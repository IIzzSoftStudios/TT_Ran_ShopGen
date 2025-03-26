from app import app

if __name__ == "__main__":
    # Run the app on all available network interfaces (0.0.0.0)
    # This allows connections from other computers on the network
    app.run(host='0.0.0.0', port=5000, debug=True) 