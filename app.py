from app import app

if __name__ == "__main__":
    app.run(debug=True)

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html", message="City not found"), 404
