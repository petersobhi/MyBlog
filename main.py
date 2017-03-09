import webapp2
import jinja2
import os
import pretty
import bcrypt
import re
import hmac
from google.appengine.ext import db
import datetime

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                               autoescape=True)
jinja_env.filters['pretty.date'] = pretty.date
jinja_env.filters['len'] = len

# database models:
class User(db.Model):
    username = db.StringProperty(required=True)
    passhash = db.StringProperty(required=True)
    email = db.StringProperty()


class Blog(db.Model):
    subject = db.StringProperty(required=True)
    blog = db.TextProperty(required=True)
    date = db.DateTimeProperty(auto_now_add=True)
    user = db.ReferenceProperty(User, collection_name='blogs')


class Comment(db.Model):
    blog = db.ReferenceProperty(Blog, collection_name='comments')
    body = db.StringProperty(required=True)
    date = db.DateTimeProperty(auto_now_add=True)
    username = db.StringProperty(required=True)


class Like(db.Model):
    blog = db.ReferenceProperty(Blog, collection_name='likes')
    username = db.StringProperty(required=True)


secret = "pJh5D?$dDW_um^S;:YQ._::m,-9dCf9<6h{@nw6g"

# create secure cookies values
def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

# check cookies values
def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val


class Handler(webapp2.RequestHandler):

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        user_cookie = self.request.cookies.get('user', False)
        self.user = None
        if user_cookie:
            u_id = check_secure_val(user_cookie)
            if u_id:
                self.user = User.get_by_id(int(u_id))

    def write(self, text):
        self.response.out.write(text)

    # render a jinja templete with custom parameters
    def render_me(self, template, **params):
        if self.user:
            params["username_nav"] = self.user.username
        t = jinja_env.get_template(template)
        rendered_text = t.render(**params)
        self.write(rendered_text)

    # parent post function for all handlers
    def post(self):
        if self.request.get("submit") == "Sign out":
            self.response.set_cookie('user', None, path='/')
            self.redirect('/blog')


class MainPage(Handler):

    def get(self):
        posts = db.GqlQuery("SELECT * FROM Blog ORDER BY date DESC").fetch(10)
        if len(posts) > 0:
            self.render_me("blog.html", posts=posts, user=self.user)
        else:
            self.render_me("blog.html", user=self.user)

    def post(self):
        super(MainPage, self).post()


class NewPost(Handler):

    def get(self):
        self.render_me("newpost.html")

    def post(self):
        super(NewPost, self).post()
        subject = self.request.get("subject")
        blog = self.request.get("blog")

        if subject and blog:
            b = Blog(subject=subject, blog=blog, user=self.user)
            b.put()
            id = b.key().id()
            self.redirect("/blog/" + str(id))
        else:
            self.render_me("newpost.html", subject=subject, blog=blog)


class BlogItem(Handler):
    # check if a blog is liked

    def blog_liked(self):
        likes = self.blog.likes
        liked = False
        for like in likes:
            if like.username == self.user.username:
                liked = True
                break
        return liked

    def count_likes(self):
        likes = self.blog.likes
        return likes.count()

    def delete(self):
        if self.blog.user.username == self.user.username:
            db.delete(self.blog)
            self.redirect('/blog/user/%s' % self.user.username)

    def edit(self, new_body):
        if self.blog.user.username == self.user.username:
            self.blog.blog = new_body
            self.blog.put()

    def delete_comment(self, comment_id):
        comment = Comment.get_by_id(int(comment_id))
        if comment.username == self.user.username:
            db.delete(comment)

    def edit_comment(self, comment_id, new_body):
        comment = Comment.get_by_id(int(comment_id))
        if comment.username == self.user.username:
            comment.body = new_body
            comment.put()

    def get(self, blog_id):
        self.blog = Blog.get_by_id(int(blog_id))
        if self.blog:
            if self.user:
                self.render_me("single.html",
                               post=self.blog,
                               user=self.user,
                               liked=self.blog_liked(),
                               likes=self.count_likes())
            else:
                self.render_me("single.html",
                               post=self.blog,
                               likes=self.count_likes())
        else:
            self.redirect('/blog')

    def post(self, blog_id):
        super(BlogItem, self).post()
        self.blog = Blog.get_by_id(int(blog_id))
        if self.user:
            if self.request.get("actype") == "delete":
                self.delete()
                return

            elif self.request.get("actype") == "edit":
                new_body = self.request.get("editedtext")
                if new_body:
                    self.edit(new_body)

            elif self.request.get("actype") == "comment":
                body = self.request.get("body")
                if body:
                    c = Comment(blog=self.blog,
                                body=body,
                                username=self.user.username)
                    c.put()

            elif self.request.get("actype") == "like":
                different_user = self.blog.user.username != self.user.username
                if not self.blog_liked() and different_user:
                    l = Like(blog=self.blog,
                             username=self.user.username)
                    l.put()

            elif self.request.get("actype") == "unlike":
                if self.blog_liked():
                    for like in self.blog.likes:
                        if like.username == self.user.username:
                            db.delete(like)

            elif self.request.get("delete_comment"):
                comment_id = self.request.get("delete_comment")
                self.delete_comment(comment_id)

            elif self.request.get("edit_comment"):
                comment_id = self.request.get("edit_comment")
                new_body = self.request.get("editedcomment")
                if new_body:
                    self.edit_comment(comment_id, new_body)

        self.redirect('/blog/'+str(blog_id))


class Register(Handler):

    def get(self):
        if not self.user:
            self.render_me("register.html")
        else:
            self.redirect('/blog')

    def post(self):
        super(Register, self).post()
        if self.request.get("submit") == "Register":
            USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
            PASSWORD_RE = re.compile(r"^.{3,20}$")
            EMAIL_RE = re.compile(r"^[\S]+@[\S]+.[\S]+$")

            username = self.request.get("username")
            password = self.request.get("password")
            repassword = self.request.get("repassword")
            email = self.request.get("email")

            err_username = not USERNAME_RE.match(username)
            err_password = not PASSWORD_RE.match(password)
            err_repassword = password != repassword
            err_email = False
            same_username = db.GqlQuery("SELECT * FROM User "
                                        "WHERE username = '%s'" % username)
            err_username_used = same_username.get() and True

            if email:
                err_email = not EMAIL_RE.match(email)

            if (err_username or err_password or err_repassword
                    or err_email or err_username_used):
                self.render_me("register.html",
                               err_username=err_username,
                               err_password=err_password,
                               err_repassword=err_repassword,
                               err_email=err_email,
                               err_username_used=err_username_used)

            else:
                passhash = bcrypt.hashpw(password, bcrypt.gensalt(2))
                u = User(username=username, passhash=passhash, email=email)
                u.put()
                u_id = u.key().id()
                u_final = make_secure_val(str(u_id))
                self.response.set_cookie('user', u_final, path='/')
                self.redirect("/blog")


class Login(Handler):

    def get(self):
        if not self.user:
            self.render_me("login.html")
        else:
            self.redirect('/blog')

    def post(self):
        # NEED TO BE MADE AS REGISTER
        USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
        PASSWORD_RE = re.compile(r"^.{3,20}$")

        username = self.request.get("username")
        password = self.request.get("password")

        err_username = not USERNAME_RE.match(username)
        err_password = not PASSWORD_RE.match(password)

        if (err_username or err_password):
            self.render_me("login.html", username=username, error=True)

        else:
            u = db.GqlQuery(
                "SELECT * FROM User WHERE username = '%s'" % username).get()
            if u:
                passhash = u.passhash
                passhash_input = bcrypt.hashpw(password, passhash)
                error = passhash != passhash_input
            else:
                error = True

            if error:
                self.render_me("login.html", username=username, error=True)
            else:
                u_id = u.key().id()
                u_final = make_secure_val(str(u_id))
                remember = self.request.get("remember")
                if remember == "on":
                    expires = datetime.datetime(2050, 1, 1, 1, 1, 1, 1)
                    self.response.set_cookie(
                        'user', u_final, path='/', expires=expires)
                else:
                    self.response.set_cookie('user', u_final, path='/')
                self.redirect("/blog")


class Profile(Handler):

    def get(self, username):
        user = User.all().filter('username =', username).get()
        if user:
            blogs = user.blogs.order('-date')
            if blogs.count() > 0:
                self.render_me("profile.html", username=username, posts=blogs)
            else:
                self.render_me("profile.html", username=username, posts=False)
        else:
            self.redirect('/blog')


class Search(Handler):
    # return True if the post has the keywords

    def find_words(self, text, search):
        dtext = text.split()
        dsearch = search.split()
        found_word = 0
        for text_word in dtext:
            for search_word in dsearch:
                if search_word.lower() == text_word.lower():
                    found_word += 1
        return found_word >= len(dsearch)

    # make search keywords bold
    def bold_keywords(self, text, search):
        dtext = text.split(' ')
        dsearch = search.split()
        final_text = ''
        for text_word in dtext:
            for search_word in dsearch:
                if search_word.lower() == text_word.lower():
                    text_word = '<b>'+text_word+'</b>'
            final_text += text_word + ' '
        return final_text

    def get(self):
        q = self.request.get("q")
        posts = db.GqlQuery("SELECT * FROM Blog ORDER BY date DESC")
        c_posts = []
        for post in posts:
            in_subject = self.find_words(post.subject, q)
            in_body = self.find_words(post.blog, q)
            if in_subject or in_body:
                post.subject = self.bold_keywords(post.subject, q)
                post.blog = self.bold_keywords(post.blog, q)
                c_posts.append(post)
        self.render_me("search.html", q=q, posts=c_posts)


app = webapp2.WSGIApplication([
    ('/blog', MainPage),
    ('/blog/newpost', NewPost),
    (r'/blog/user/(\w+)', Profile),
    (r'/blog/(\d+)', BlogItem),
    ('/blog/register', Register),
    ('/blog/login', Login),
    ('/blog/search', Search)
], debug=True)
