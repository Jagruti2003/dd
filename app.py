import os
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from helpers import apology, login_required, lookup, usd

app = Flask(__name__)

app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")



@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]

    # Get user's stocks and shares
    stocks = db.execute(
        "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
        user_id=user_id
    )

    # Get user's cash balance
    cash_row = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=user_id)
    if not cash_row:
        return apology("User not found", 400)
    cash = cash_row[0]["cash"]

    # Initialize variables for total values
    total_value = cash
    grand_total = cash

    # Iterate over stocks and add price and total value
    for stock in stocks:
        quote = lookup(stock["symbol"])
        if quote and "price" in quote:
            stock["name"] = quote.get("name", "N/A")
            stock["price"] = quote["price"]
            stock["value"] = stock["price"] * stock["total_shares"]
            total_value += stock["value"]
            grand_total += stock["value"]
        else:
            stock["name"] = "N/A"
            stock["price"] = 0
            stock["value"] = 0

    return render_template("index.html", stocks=stocks, cash=cash, total_value=total_value, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")

        # Validate symbol and shares inputs
        if not symbol:
            return apology("Must provide symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("Must provide a positive integer number of shares")

        quote = lookup(symbol)
        if quote is None:
            return apology("Symbol not found")

        price = quote["price"]
        total_cost = int(shares) * price

        # Get the user's current cash balance
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id",
                          user_id=session["user_id"])[0]["cash"]

        if cash < total_cost:
            return apology("Not enough cash")

        # Update the user's cash balance
        db.execute("UPDATE users SET cash = cash - :total_cost WHERE id = :user_id",
                   total_cost=total_cost, user_id=session["user_id"])

        # Add the purchase to the transactions table
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"], symbol=symbol, shares=int(shares), price=price)

        flash(f"Bought {shares} shares of {symbol} for {usd(total_cost)}!")
        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query database for user's transactions, ordered by most recent first
    transactions = db.execute(
        "SELECT * FROM transactions WHERE user_id = :user_id ORDER BY timestamp DESC",
        user_id=session["user_id"]
    )
    # Render history page with transactions
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username:
            return apology("Must provide username", 403)
        elif not password:
            return apology("Must provide password", 403)

        user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(user) != 1 or not check_password_hash(user[0]["hash"], password):
            return apology("Invalid username and/or password", 403)

        session["user_id"] = user[0]["id"]
        return redirect("/")

    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not quote:
            return apology("Invalid symbol", 400)
        return render_template("quoted.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("Must provide username", 400)
        elif not password:
            return apology("Must provide password", 400)
        elif password != confirmation:
            return apology("Passwords do not match", 400)

        try:
            hashed_password = generate_password_hash(password)
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                       username, hashed_password)
            user = db.execute("SELECT * FROM users WHERE username = ?", username)
            session["user_id"] = user[0]["id"]
            return redirect("/")
        except:
            return apology("Username already exists", 400)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        if not symbol:
            return apology("Must provide symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("Must provide a positive integer number of shares")

        shares = int(shares)
        stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                            user_id=session["user_id"])

        for stock in stocks:
            if stock["symbol"] == symbol:
                if stock["total_shares"] < shares:
                    return apology("Not enough shares")
                else:
                    quote = lookup(symbol)
                    if quote is None:
                        return apology("Symbol not found")

                    price = quote["price"]
                    total_sale = shares * price

                    db.execute("UPDATE users SET cash = cash + :total_sale WHERE id = :user_id",
                               total_sale=total_sale, user_id=session["user_id"])

                    db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price)",
                               user_id=session["user_id"], symbol=symbol, shares=-shares, price=price)

                    flash(f"Sold {shares} shares of {symbol} for {usd(total_sale)}!")
                    return redirect("/")

        return apology("Symbol not found")
    else:
        stocks = db.execute("SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0",
                            user_id=session["user_id"])
        return render_template("sell.html", stocks=stocks)


if __name__ == "__main__":
    app.run(debug=True)
