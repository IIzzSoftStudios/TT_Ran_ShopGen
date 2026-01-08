"""
Email Service
Handles sending emails for verification, password reset, and 2FA
"""
from flask import current_app, render_template
from app.extensions import mail
from flask_mail import Message
from app.services.logging_config import auth_logger


def send_email(subject, recipients, template, **kwargs):
    """
    Send an email using Flask-Mail
    
    Args:
        subject: Email subject
        recipients: List of recipient email addresses
        template: Template name (without .html extension)
        **kwargs: Additional context variables for the template
    """
    try:
        msg = Message(
            subject=subject,
            recipients=recipients,
            html=render_template(f'emails/{template}.html', **kwargs),
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        mail.send(msg)
        auth_logger.info(f"Email sent successfully to {recipients} - Subject: {subject}")
        return True
    except Exception as e:
        auth_logger.error(f"Failed to send email to {recipients}: {str(e)}", exc_info=True)
        return False


def send_verification_email(user):
    """Send email verification email to user"""
    token = user.generate_verification_token()
    verification_url = f"{current_app.config['BASE_URL']}/auth/verify-email/{token}"
    app_name = current_app.config['APP_NAME']
    
    return send_email(
        subject=f"Verify your {app_name} account",
        recipients=[user.email],
        template='verify_email',
        user=user,
        verification_url=verification_url,
        app_name=app_name
    )


def send_password_reset_email(user):
    """Send password reset email to user"""
    token = user.generate_reset_token()
    reset_url = f"{current_app.config['BASE_URL']}/auth/reset-password/{token}"
    app_name = current_app.config['APP_NAME']
    
    return send_email(
        subject=f"Reset your {app_name} password",
        recipients=[user.email],
        template='reset_password_email',
        user=user,
        reset_url=reset_url,
        app_name=app_name
    )


def send_2fa_code_email(user, code):
    """Send 2FA code via email (alternative to TOTP)"""
    app_name = current_app.config['APP_NAME']
    
    return send_email(
        subject=f"Your {app_name} 2FA code",
        recipients=[user.email],
        template='2fa_code',
        user=user,
        code=code,
        app_name=app_name
    )

