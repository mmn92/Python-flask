import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

from datetime import datetime

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Retrieve all the info from the user from the db
    db_users = db.execute("SELECT * FROM users JOIN stocks ON users.id = stocks.id "
                          "JOIN companies ON stocks.companyId = companies.companyId "
                          "WHERE users.id = :user_Id",
                          user_Id=session["user_id"]
                          )

    if not db_users:
        db_balance = db.execute("SELECT cash from users WHERE id = :user_Id",
                                user_Id=session["user_id"]
                                )
        return render_template("index.html", stocks=0, user_balance=db_balance[0]["cash"])

    # This dict will hold the prices of the stocks
    stock_price = {}
    shares_sum = 0
    balance = db_users[0]["cash"]

    for row in db_users:
        stock_price[row["company"]] = float(lookup(row["symbol"])["price"])
        shares_sum += int(row["shares"]) * float(lookup(row["symbol"])["price"])

    return render_template("index.html", db_info=db_users, prices=stock_price,
                           stocks=shares_sum, user_balance=balance)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure stock symbol was submitted
        if not request.form.get("symbol"):
            return apology("No symbol", 400)

        try:
            a = int(request.form.get("shares"))
        except ValueError:
            return apology("not an integer", 400)

        # Ensure amount of shares was submitted
        if not request.form.get("shares") or int(request.form.get("shares")) < 1:
            return apology("No shares amount", 400)

        else:

            info = lookup(request.form.get("symbol"))

            if not info:
                return apology("invalid symbol", 400)

            rows = db.execute("SELECT * FROM users WHERE id = :user_Id",
                              user_Id=session["user_id"])
            if len(rows) != 1:
                return apology("invalid user ID", 400)

            # Inserts new company - nothing happens if company already in db
            db.execute("INSERT INTO companies (company, symbol) "
                       "VALUES(:company, :symbol)",
                       company=info["name"],
                       symbol=info["symbol"],
                       )

            company_info = db.execute("SELECT * FROM companies WHERE company = :company",
                                      company=info["name"]
                                      )

            if not company_info:
                return apology("an error ocurred while fetching company info", 403)
            else:
                company_id = int(company_info[0]["companyId"])

            # Pulls info from stocks
            user_check = db.execute("SELECT * FROM stocks JOIN companies ON stocks.companyId = "
                                    "companies.companyId WHERE stocks.id = :user_Id AND "
                                    "companies.companyId = :company_id",
                                    user_Id=session["user_id"],
                                    company_id=company_id
                                    )

            # Ensures the user has enough money
            if float(rows[0]["cash"]) < float(info["price"]) * int(request.form.get("shares")):
                return apology("not enough cash", 403)

            # Checks if user already has shares of the company
            elif not user_check:

                # Inserts user stock info
                db.execute("INSERT INTO stocks (shares, companyId, id) "
                           "VALUES(:shares, :companyId, :user_Id)",
                           shares=request.form.get("shares"),
                           companyId=company_id,
                           user_Id=session["user_id"]
                           )

            # User already has stocks from the company
            else:

                # Updates user stock info
                db.execute("UPDATE stocks SET shares = :shares "
                           "WHERE companyId = :companyId",
                           shares=int(user_check[0]["shares"]) + int(request.form.get("shares")),
                           companyId=company_id,
                           )

            # Updates user balance
            db.execute("UPDATE users SET cash = :value WHERE id = :user_Id",
                       value=rows[0]["cash"] - (float(info["price"]) * int(request.form.get("shares"))),
                       user_Id=session["user_id"]
                       )

            # Inserts new transaction TODO
            db.execute("INSERT INTO transactions (type, day, shares, price, companyId, id) "
                       "VALUES(:type_, :day, :shares, :price, :companyId, :custId)",
                       type_="buy",
                       day=datetime.now(),
                       shares=int(request.form.get("shares")),
                       price=float(info["price"]) * int(request.form.get("shares")),
                       companyId=company_id,
                       custId=session["user_id"]
                       )

            return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # users JOIN  transactions JOIN companies
    db_user = db.execute("SELECT * FROM users JOIN transactions ON "
                         "users.id = transactions.id JOIN companies ON "
                         "transactions.companyId = companies.companyId WHERE "
                         "users.id = :user_id",
                         user_id=session["user_id"]
                         )

    # Ensures there was a valid search
    if not db_user:
        return apology("no history found", 403)

    else:
        return render_template("history.html", db_info=db_user)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/passchange", methods=["GET", "POST"])
@login_required
def change_password():
    """Changes password for user"""

    # if request method was POST, execute password change
    if request.method == "POST":
        if not request.form.get("old_password"):
            return apology("you must provide your old password", 403)
        elif not request.form.get("password"):
            return apology("you must provide a new password", 403)
        elif not request.form.get("confirmation") or request.form.get("password") != request.form.get("confirmation"):
            return apology("invalid confirmation", 403)
        else:
            rows = db.execute("SELECT * FROM users WHERE id = :user_Id",
                       user_Id=session["user_id"]
                       )
            if not check_password_hash(rows[0]["hash"], request.form.get("old_password")):
                return apology("invalid password", 403)
            else:
                db.execute("UPDATE users SET hash = :new_hash WHERE id = :user_Id",
                           new_hash=generate_password_hash(request.form.get("password")),
                           user_Id=session["user_id"]
                           )

                return redirect("/login")

    # if request method was GET, simply show the password change page
    else:
        return render_template("passChange.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide a stock name", 400)

        else:
            info = lookup(request.form.get("symbol"))
            if not info:
                return apology("invalid name", 400)
            else:
                return render_template("quoted.html", quote=info)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # Ensure password and confirmation are the same
        else:
            if request.form.get("password") != request.form.get("confirmation"):
                return apology("passwords must match", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure the username is not being used
        if len(rows) > 0:
            return apology("username already registered", 400)

        # Registers username in db
        else:
            db.execute("INSERT INTO users (username, hash) VALUES(:username, :hashed)",
                       username=request.form.get("username"),
                       hashed=generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # Ensure the user submitted a symbol
        if not request.form.get("symbol"):
            return apology("select a stock", 400)

        # Ensures the user has submitted a valid number
        elif not request.form.get("shares") or int(request.form.get("shares")) < 1:
            return apology("invalid share numbers", 400)

        db_users = db.execute("SELECT * FROM users JOIN stocks ON users.id = stocks.id "
                              "JOIN companies ON stocks.companyId = companies.companyId "
                              "WHERE companies.symbol = :symbol AND users.id = :user_id",
                              symbol=request.form.get("symbol"),
                              user_id=session["user_id"]
                              )

        # Ensures the entry exists
        if not db_users:
            return apology("invalid stock", 400)

        # Ensures there is only one row with the symbol
        elif len(db_users) > 1:
            return apology("an error ocurred", 400)

        # Ensure the user has enough of the shares
        if int(request.form.get("shares")) > int(db_users[0]["shares"]):
            return apology("not enough shares", 400)

        # The user has the selected shares
        else:
            value = lookup(request.form.get("symbol"))

            # Ensures the request worked
            if not value:
                return apology("an error ocurred", 400)

            # Checks if the user has exactly the number of shares to sell
            if int(request.form.get("shares")) == int(db_users[0]["shares"]):
                # Delete row
                db.execute("DELETE FROM stocks WHERE companyId = :company_id "
                           "AND id = :user_id",
                           company_id=db_users[0]["companyId"],
                           user_id=session["user_id"]
                           )

            # Checks if the user has more shares than the amount to sell
            else:
                # Update row
                db.execute("UPDATE stocks SET shares = :shares WHERE companyId = :company_id "
                           "AND id = :user_id",
                           shares=int(db_users[0]["shares"]) - int(request.form.get("shares")),
                           company_id=db_users[0]["companyId"],
                           user_id=session["user_id"]
                           )

            # Updates the user balance
            db.execute("UPDATE users SET cash = :value WHERE id = :user_Id",
                       value=float(db_users[0]["cash"]) + (value["price"] * int(request.form.get("shares"))),
                       user_Id=session["user_id"]
                       )

            # Inserts the the transaction in history
            db.execute("INSERT INTO transactions (type, day, shares, price, companyId, id) "
                       "VALUES(:type_, :day, :shares, :price, :companyId, :custId)",
                       type_="sell",
                       day=datetime.now(),
                       shares=int(request.form.get("shares")),
                       price=float(value["price"]) * int(request.form.get("shares")),
                       companyId=db_users[0]["companyId"],
                       custId=session["user_id"]
                       )

            return redirect("/")

    else:
        db_users = db.execute("SELECT * FROM stocks JOIN companies ON "
                              "stocks.companyId = companies.companyId WHERE id = :user_Id",
                              user_Id=session["user_id"]
                              )
        info = []
        for rows in db_users:
            info.append((rows["symbol"], rows["company"]))
        return render_template("sell.html", info=info)


def errorhandler(e):
    """Handle error"""
    return apology(e.name, e.code)


# listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
