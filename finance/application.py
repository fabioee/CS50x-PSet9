import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

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

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Check the amount of cash the user has
    cash_available = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]
    
    # Declare variable to tabulate total assets in portfolio
    total = cash_available
    
    # Retrieve user portfolio
    portfolio = db.execute("SELECT stock_symbol, stock_name, number_of_shares FROM portfolio WHERE user_id=?", session["user_id"])
    
    # For each stoc in the user's portfolio
    for stock in portfolio:
        # Look up the current price of the stock
        price = lookup(stock["stock_symbol"])["price"]
        # Record the value of the user's shares
        total_value = price * stock["number_of_shares"]
        # Update the stock in the portfolio based on the current price
        stock.update({"price": price, "total_value": total_value})
        # Record the total value of all the stocks and cash the user has
        total += total_value
    
    # Render the template and return the portfoilio to the user
    return render_template("index.html", portfolio=portfolio, cash=cash_available, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        # Record user inputs
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        quote = lookup(symbol)
        
        # If no stock is requested for purchase, apologize
        if not symbol:
            return apology("invalid request, please add stock", 400)
        # If does not exist, apologize
        elif quote == None:
            return apology("invalid request, stock does not exist", 400)
        # If number of shares is blank, apologize
        elif shares == "":
            return apology("invalid request, share must be at least 1", 400)
        # If the shares entered are non-numeric, apologize
        elif shares.isalpha() == True:
            return apology("invalid request, share must be a whole number", 400)
        elif shares.isnumeric() == False:
            return apology("invalid request, share must be a whole number", 400)
        # If shares for purchase are less than 1, apologize
        elif int(float(shares)) < 1:
            return apology("invalid request, share must be at least 1", 400)
        else:
            # Check the user's cash available
            available_funds = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]
            
            # Calculate the cost of the purchase
            cost = quote["price"] * int(shares)
            
            # If the purchase will cost more than the user has cash, apologize
            if cost > available_funds:
                return apology("invalid request, insufficient funds for number of shares", 400)
            else:
                # Record transaction type
                transaction_type = "PURCHASED"
                
                # Keep tack of user
                username = db.execute("SELECT username FROM users WHERE id=?", session["user_id"])[0]["username"]
                
                # Update the user's cash amount
                db.execute("UPDATE users SET cash=cash-:cost WHERE id=:id", cost=cost, id=session["user_id"])
                # Record the transaction
                db.execute("INSERT INTO transactions (user_id, username, stock_symbol, number_of_shares, price, transaction_type) VALUES(?, ?, ?, ?, ?, ?)",
                           session["user_id"], username, quote["symbol"], shares, quote["price"], transaction_type)
                
                # Check if the purchased stock already exists in the portfolio
                check = db.execute("SELECT * FROM portfolio WHERE user_id = ? AND stock_symbol = ?",
                                   session["user_id"],  quote["symbol"])
                
                # If not, add the stock
                if not check:
                    db.execute("INSERT INTO portfolio (user_id, stock_symbol, stock_name, number_of_shares) VALUES(?, ?, ?, ?)",
                               session["user_id"], quote["symbol"], quote["name"], shares)
                # If so, update the stock
                else:
                    db.execute("UPDATE portfolio SET number_of_shares=number_of_shares+:shares WHERE stock_symbol=:symbol",
                               shares=shares, symbol=quote["symbol"])
            return redirect("/")
                
    # IF GET method request, render buy template       
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT * FROM transactions WHERE user_id=?", session["user_id"])
        
    return render_template("history.html", transactions=transactions)
    

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

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

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

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
        # Get the stock symbol from the user input
        symbol = request.form.get("symbol")
        
        # If there is no stock entered, apologize
        if not symbol:
            return apology("invalid request, please add stock", 400)
        # If the stock doesn't exist, apologize
        if lookup(symbol) == None:
            return apology("invalid request, stock does not exist", 400)
        else:
            # Otherwise, get a dictionary of the stocks name, price, and symbol
            quote = lookup(symbol)
            # Render the quote to the template
            return render_template("quoted.html", quote=quote)
    # If GET method is requested, render quote template
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        # Ensure passsword length
        elif len(request.form.get("password")) < 6:
            return apology("password must be at least 6 characters", 400)
        # Ensure password confirmation
        elif not request.form.get("confirmation"):
            return apology("must re-enter password", 400)
    
        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
    
        # Ensure username is unique and passwords match
        if len(rows) != 1 and (request.form.get("password")) == request.form.get("confirmation"):
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get(
                "username"), generate_password_hash(request.form.get("password")))
            
            # Find new user in users
            rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
            
            # Remember the new user
            session["user_id"] = rows[0]["id"]
            
            # Log them in
            return redirect("/")
        
        # If username is not unique, apologize
        elif len(rows) > 0:
            return apology("username already exists", 400)
        # If passdords do not match, apologize
        elif (request.form.get("password")) != request.form.get("confirmation"):
            return apology("passwords do not match", 400)
    
    # Render register template when GET method is called
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        quote = lookup(symbol)
        
        # If the symbol is blank, apologize
        if not symbol:
            return apology("invalid request, please select stock", 400)
        # If the stock does not exist, apologize
        elif quote == None:
            return apology("invalid request, stock does not exist", 400)
        # If shares are left blank, apologize
        elif shares == "":
            return apology("invalid request, share must be at least 1", 400)
        # If shares are less than 1, apologize
        elif float(shares) < 1:
            return apology("invalid request, share must be at least 1", 400)
        # If the shares are non-numerical, apologize
        elif not shares.isdigit():
            return apology("invalid request, share must be a number", 400)
        else:
            # Check the number of shares currently owned
            check_shares = db.execute(
                "SELECT number_of_shares FROM portfolio WHERE user_id=? AND stock_symbol = ?", session["user_id"], quote["symbol"])
            
            # If owned less than wanting to sell, apologize
            if check_shares[0]["number_of_shares"] < int(shares):
                return apology("number of stocks owned are less than requested to be sold", 400)
            # If no shares exist, apologize
            elif not check_shares:
                return apology("you do not own any shares of this stock", 400)
            else:
                # Otherwise, calculate how much the amount of shares will profit based on current stock price
                cost = quote["price"] * int(shares)
                transaction_type = "SOLD"
                
                # Keep track of the user
                username = db.execute("SELECT username FROM users WHERE id=?", session["user_id"])[0]["username"]
                
                # Add the cash from the stocks sold to the user's cash
                db.execute("UPDATE users SET cash=cash+:cost WHERE id=:id", cost=cost, id=session["user_id"])
                
                # Record the transaction
                db.execute("INSERT INTO transactions (user_id, username, stock_symbol, number_of_shares, price, transaction_type) VALUES(?, ?, ?, ?, ?, ?)",
                           session["user_id"], username, quote["symbol"], shares, quote["price"], transaction_type)
                
                # Update the portfolio based on the transaction
                db.execute("UPDATE portfolio SET number_of_shares=number_of_shares-:shares WHERE stock_symbol=:symbol",
                           shares=shares, symbol=quote["symbol"])
                
                # Check how many shares the user has after the transaction
                check = db.execute("SELECT number_of_shares FROM portfolio WHERE user_id=? AND stock_symbol = ?",
                                   session["user_id"], quote["symbol"])
                
                # If no shares are held, remove the stock from the portfolio
                if check[0]["number_of_shares"] == 0:
                    db.execute("DELETE FROM portfolio WHERE stock_symbol = ?", quote["symbol"])
                
            return redirect("/")
                
    # If GET metod is requested, render sell page with stocks in portfolio that the user has shares in
    else:
        portfolio = db.execute("SELECT stock_symbol FROM portfolio WHERE user_id=?", session["user_id"])
        
        return render_template("sell.html", portfolio=portfolio)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)


@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    """Update user password"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)
        # Ensure current password was submitted
        elif not request.form.get("current_password"):
            return apology("must provide current password", 400)
        # Ensure new password was submitted
        elif not request.form.get("new_password"):
            return apology("must provide new password", 400)
        # Ensure new password length
        elif len(request.form.get("new_password")) < 6:
            return apology("new_password must be at least 6 characters", 400)
        # Ensure password confirmation
        elif not request.form.get("new_password_confirmation"):
            return apology("must re-enter password", 400)
    
        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
    
        # Ensure username is correct is unique and passwords match
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("current_password")):
            return apology("invalid username and/or password", 400)
        # If passwords do not match, apologize
        elif (request.form.get("new_password")) != request.form.get("new_password_confirmation"):
            return apology("passwords do not match", 400)
        
        # If the username exists and the current password is correct and the new password matches the confirmation, update the user password
        if len(rows) == 1 and check_password_hash(rows[0]["hash"], request.form.get("current_password")) and (request.form.get("new_password")) == request.form.get("new_password_confirmation"):
            db.execute("UPDATE users SET hash=:password WHERE username=:username", password=generate_password_hash(
                request.form.get("new_password")), username=request.form.get("username"))
            
            # Remember the new user
            session["user_id"] = rows[0]["id"]
            
            # Log them in
            return redirect("/")
    
    # Render change_password template when GET method is called
    else:
        return render_template("change_password.html")
