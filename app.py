import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Query database for users stock portfolio, assigned in main portfolio list
    stocks_owned = db.execute(
        "SELECT name, symbol, stock_id FROM history JOIN stocks ON history.stock_id = stocks.id WHERE user_id = ? GROUP BY stock_id", session['user_id'])
    cash_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    for i in range(len(stocks_owned)):
        # Lookup current price for each stock and add to main portfolio list
        stocks_owned[i]["current_price"] = lookup(stocks_owned[i]["symbol"])["price"]

        # Count every buy transaction from database for each stock user has
        stocks_bought = (db.execute("SELECT SUM(quantity) FROM history JOIN stocks ON history.stock_id = stocks.id WHERE user_id = ? AND buy_sell = 'BUY' AND stock_id = ? GROUP BY stock_id",
                                   session['user_id'], stocks_owned[i]['stock_id']))[0]["SUM(quantity)"]
        # Count every sell transaction from database for each stock user has
        stocks_sold = db.execute("SELECT SUM(quantity) FROM history JOIN stocks ON history.stock_id = stocks.id WHERE user_id = ? AND buy_sell = 'SELL' AND stock_id = ? GROUP BY stock_id",
                                 session['user_id'], stocks_owned[i]['stock_id'])

        #
        if len(stocks_sold) < 1:
            stocks_sold = 0
        else:
            stocks_sold = stocks_sold[0]["SUM(quantity)"]

        stock_qty = stocks_bought - stocks_sold

        stocks_owned[i]["stock_qty"] = stock_qty

        stocks_owned[i]["total_value"] = stock_qty * stocks_owned[i]["current_price"]

        if stock_qty == 0:
            stocks_owned[i] = []

    return render_template("index.html", stocks=stocks_owned, cash_balance=cash_balance)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("No Symbol Input")
        if not request.form.get("shares"):
            return apology("No Shares Input")
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        try:
            float(shares)
        except ValueError:
            return apology("Invalid Number of Shares")
        if int(float(shares)) < 1:
            return apology("Invalid Number of Shares")
        if not shares.isdigit():
            return apology("Invalid Number of Shares")
        if not lookup(request.form.get("symbol")):
            return apology("Invalid Symbol")
        price = lookup(symbol)["price"]
        cash_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        if (float(shares)*price) > cash_balance[0]['cash']:
            return apology("Not Enough Cash")
        if db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol):
            stock_id = db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol)[0]['id']
        else:
            db.execute("INSERT INTO stocks (symbol, name) VALUES (?, ?)", symbol, lookup(symbol)["name"])
            stock_id = db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol)[0]['id']

        db.execute("INSERT INTO history (stock_id, price, quantity, user_id, buy_sell, time) VALUES (?, ?, ?, ?, 'BUY', julianday('now'))",
                   stock_id, price, shares, session["user_id"])
        new_cash_balance = cash_balance[0]["cash"] - (float(shares) * price)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash_balance, session["user_id"])
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transaction_history = db.execute(
        "SELECT symbol, name, price, quantity, buy_sell, datetime(time) FROM history JOIN stocks ON stocks.id = history.stock_id WHERE user_id = ? ORDER BY datetime(time) DESC", session['user_id'])
    for i in range(len(transaction_history)):
        transaction_value = transaction_history[i]["quantity"] * float(transaction_history[i]["price"])
        transaction_history[i]["transaction_value"] = transaction_value

        transaction_history[i]["price"] = transaction_history[i]["price"]

        transaction_history[i]["date"] = (
            (datetime.strptime(transaction_history[i]["datetime(time)"], '%Y-%m-%d %H:%M:%S')) + timedelta(hours=3)).date()
        transaction_history[i]["time"] = (
            (datetime.strptime(transaction_history[i]["datetime(time)"], '%Y-%m-%d %H:%M:%S')) + timedelta(hours=3)).time()

    cash_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
    return render_template("history.html", cash_balance=cash_balance, transaction_history=transaction_history)


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
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

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
            return apology("no symbol input")
        symbol = lookup(request.form.get("symbol"))
        if not symbol:
            return apology("invalid symbol")
        return render_template("quote.html", symbols=symbol)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username")
        if not request.form.get("password"):
            return apology("must provide password ")
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match")
        currentUsers = db.execute("SELECT username FROM users")
        current = []
        for user in currentUsers:
            for val in user.values():
                current.append(val)
        if request.form.get("username") in current:
            return apology("username is already taken")
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)",
                   request.form.get("username"), generate_password_hash(request.form.get("password")))
        session["user_id"] = (db.execute("SELECT id FROM users WHERE username = ?", request.form.get("username")))[0]["id"]
        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    stocks_involved = db.execute(
        "SELECT stock_id, name, symbol FROM history JOIN stocks ON history.stock_id = stocks.id WHERE user_id = ? GROUP BY stock_id", session['user_id'])
    possible_sells = []
    for i in range(len(stocks_involved)):
        stocks_bought = db.execute(
            "SELECT SUM(quantity) FROM history JOIN stocks ON history.stock_id = stocks.id WHERE user_id = ? AND buy_sell = 'BUY' AND stock_id = ? GROUP BY stock_id", session['user_id'], stocks_involved[i]['stock_id'])
        stocks_sold = db.execute(
            "SELECT SUM(quantity) FROM history JOIN stocks ON history.stock_id = stocks.id WHERE user_id = ? AND buy_sell = 'SELL' AND stock_id = ? GROUP BY stock_id", session['user_id'], stocks_involved[i]['stock_id'])
        if len(stocks_bought) < 1:
            stocks_bought = 0
        else:
            stocks_bought = stocks_bought[0]["SUM(quantity)"]
        if len(stocks_sold) < 1:
            stocks_sold = 0
        else:
            stocks_sold = stocks_sold[0]["SUM(quantity)"]

        if (stocks_bought - stocks_sold) > 0:
            possible_sell_item = {"stock_id": stocks_involved[i]["stock_id"], "name": stocks_involved[i]["name"],
                                  "symbol": stocks_involved[i]["symbol"], "shares": stocks_bought - stocks_sold}
            possible_sells.append(possible_sell_item)

    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("no symbol input")
        if not request.form.get("shares"):
            return apology("no number of shares input")
        if int(request.form.get("shares")) < 1:
            return apology("invalid number of shares")
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        if not db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol):
            return apology("invalid symbol")

        stock_id = (db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol))[0]["id"]
        stocks_bought = db.execute(
            "SELECT SUM(quantity) FROM history JOIN stocks ON history.stock_id = stocks.id WHERE user_id = ? AND buy_sell = 'BUY' AND stock_id = ? GROUP BY stock_id", session['user_id'], stock_id)
        stocks_sold = db.execute(
            "SELECT SUM(quantity) FROM history JOIN stocks ON history.stock_id = stocks.id WHERE user_id = ? AND buy_sell = 'SELL' AND stock_id = ? GROUP BY stock_id", session['user_id'], stock_id)

        if len(stocks_bought) < 1:
            stocks_bought = 0
        else:
            stocks_bought = stocks_bought[0]["SUM(quantity)"]
        if len(stocks_sold) < 1:
            stocks_sold = 0
        else:
            stocks_sold = stocks_sold[0]["SUM(quantity)"]

        stock_owned = stocks_bought - stocks_sold
        if stock_owned < int(shares):
            return apology("you do not own enough shares")
        price = lookup(symbol)["price"]
        cash_balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        db.execute("INSERT INTO history (stock_id, price, quantity, user_id, buy_sell, time) VALUES (?, ?, ?, ?, 'SELL', julianday('now'))",
                   stock_id, price, shares, session["user_id"])
        new_cash_balance = cash_balance[0]["cash"] + (float(shares) * price)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash_balance, session["user_id"])
        return redirect("/")

    else:
        return render_template("sell.html", possible_sells=possible_sells)