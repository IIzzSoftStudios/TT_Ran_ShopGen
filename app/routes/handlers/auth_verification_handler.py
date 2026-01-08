"""
Auth Verification Handler
Handles email verification functionality
"""
from flask import render_template, redirect, url_for, flash, request
from app.models.users import User
from app.services.logging_config import auth_logger
from app.services.email_service import send_verification_email


def handle_verify_email(token):
    """Handle email verification with token"""
    if not token:
        flash("Invalid verification link!", "error")
        return redirect(url_for("auth.login"))
    
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        flash("Invalid or expired verification link!", "error")
        return redirect(url_for("auth.login"))
    
    if not user.verify_email_token(token):
        flash("Verification link has expired! Please request a new one.", "error")
        return redirect(url_for("auth.resend_verification"))
    
    # Verify the email
    user.verify_email()
    auth_logger.info(f"Email verified for user: {user.username}")
    flash("Email verified successfully! You can now log in.", "success")
    return redirect(url_for("auth.login"))


def handle_resend_verification():
    """Handle resending verification email"""
    if request.method == "POST":
        email = request.form.get("email")
        
        if not email:
            flash("Email is required!", "warning")
            return redirect(url_for("auth.resend_verification"))
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Don't reveal if email exists for security
            flash("If an account with that email exists, a verification email has been sent.", "info")
            return redirect(url_for("auth.login"))
        
        if user.email_verified:
            flash("This email is already verified!", "info")
            return redirect(url_for("auth.login"))
        
        # Send verification email
        try:
            if send_verification_email(user):
                auth_logger.info(f"Resent verification email to {email}")
                flash("Verification email sent! Please check your inbox.", "success")
            else:
                flash("Failed to send verification email. Please try again later.", "error")
        except Exception as e:
            auth_logger.error(f"Error resending verification email: {str(e)}", exc_info=True)
            flash("There was an error sending the verification email. Please try again later.", "error")
        
        return redirect(url_for("auth.login"))
    
    # GET request - show form
    return render_template("resend_verification.html")

