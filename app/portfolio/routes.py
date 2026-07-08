from flask import Blueprint, render_template


portfolio = Blueprint(
    "portfolio",
    __name__
)


@portfolio.route("/")
def home():
    return render_template("base.html")
