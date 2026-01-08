"""
Auth Password Handler
Handles password reset and recovery functionality
"""
from flask import render_template, redirect, url_for, flash, request
from app.models.users import User
from app.services.logging_config import auth_logger
from app.services.email_service import send_password_reset_email


def handle_forgot_password():
    """Handle password reset requests"""
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        auth_logger.info(f"Password reset requested for username: {username}, email: {email}")
        
        # Allow reset by username or email
        if not username and not email:
            flash("Please provide either username or email!", "warning")
            return redirect(url_for("auth.forgot_password"))
            
        user = None
        if username:
            user = User.query.filter_by(username=username).first()
        elif email:
            user = User.query.filter_by(email=email).first()
            
        if user:
            # Send password reset email
            try:
                if send_password_reset_email(user):
                    auth_logger.info(f"Password reset email sent to {user.email}")
                    flash("If an account with that email exists, a password reset link has been sent.", "info")
                else:
                    auth_logger.warning(f"Failed to send password reset email to {user.email}")
                    flash("There was an error sending the reset email. Please try again later.", "error")
            except Exception as e:
                auth_logger.error(f"Error sending password reset email: {str(e)}", exc_info=True)
                flash("There was an error sending the reset email. Please try again later.", "error")
        else:
            # Don't reveal if username/email exists for security
            flash("If an account with that information exists, a password reset link has been sent.", "info")
        
        return redirect(url_for("auth.login"))
    
    return render_template("forgot_password.html")


def handle_reset_password(token):
    """Handle password reset with token"""
    if request.method == "POST":
        new_password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        if not new_password or not confirm_password:
            flash("All fields are required!", "warning")
            return redirect(url_for("auth.reset_password", token=token))
            
        if new_password != confirm_password:
            flash("Passwords do not match!", "warning")
            return redirect(url_for("auth.reset_password", token=token))
            
        # Find user with this token
        user = User.query.filter_by(reset_token=token).first()
        if not user or not user.verify_reset_token(token):
            flash("Invalid or expired reset token!", "error")
            return redirect(url_for("auth.forgot_password"))
            
        # Update password
        user.set_password(new_password)
        user.clear_reset_token()
        auth_logger.info(f"Password reset successful for user: {user.username}")
        flash("Password updated successfully! You can now log in.", "success")
        return redirect(url_for("auth.login"))
    
    # GET request - show reset form
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        flash("Invalid or expired reset token!", "error")
        return redirect(url_for("auth.forgot_password"))
        
    return render_template("reset_password.html", token=token)


def handle_admin_reset():
    """Admin utility to generate reset token for testing"""
    auth_logger.info(f"Admin reset called with method: {request.method}")
    auth_logger.info(f"Form data: {request.form}")
    auth_logger.info(f"Args data: {request.args}")
    
    if request.method == "POST":
        username = request.form.get("username")
        auth_logger.info(f"POST - Username from form: {username}")
    else:
        username = request.args.get("username")
        auth_logger.info(f"GET - Username from args: {username}")
        
    if not username:
        auth_logger.warning("No username provided")
        flash("Username is required!", "warning")
        return redirect(url_for("gm.gm_home"))
        
    user = User.query.filter_by(username=username).first()
    if not user:
        auth_logger.warning(f"User not found: {username}")
        flash(f"User '{username}' not found!", "error")
        return redirect(url_for("gm.gm_home"))
        
    token = user.generate_reset_token()
    auth_logger.info(f"Admin generated reset token for user: {username}")
    flash(f"Reset token for {username}: {token}", "info")
    return redirect(url_for("auth.reset_password", token=token))

