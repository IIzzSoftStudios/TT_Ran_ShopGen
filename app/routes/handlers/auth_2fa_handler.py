"""
Auth 2FA Handler
Handles two-factor authentication setup and verification
"""
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from app.models.users import User
from app.services.logging_config import auth_logger
import pyotp
import qrcode
import io
import base64


def handle_2fa_setup():
    """Handle 2FA setup"""
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "enable":
            # Generate secret if not exists
            if not current_user.two_factor_secret:
                secret = pyotp.random_base32()
                current_user.two_factor_secret = secret
                current_user.generate_backup_codes()
                from app.extensions import db
                db.session.commit()
            
            # Verify the code before enabling
            code = request.form.get("code")
            if not code:
                flash("Please enter the verification code!", "warning")
                return redirect(url_for("auth.two_factor_setup"))
            
            totp = pyotp.TOTP(current_user.two_factor_secret)
            if totp.verify(code, valid_window=1):
                current_user.two_factor_enabled = True
                from app.extensions import db
                db.session.commit()
                auth_logger.info(f"2FA enabled for user: {current_user.username}")
                flash("Two-factor authentication enabled successfully!", "success")
                return redirect(url_for("auth.two_factor_setup"))
            else:
                flash("Invalid verification code! Please try again.", "error")
                return redirect(url_for("auth.two_factor_setup"))
        
        elif action == "disable":
            password = request.form.get("password")
            if not password or not current_user.check_password(password):
                flash("Incorrect password!", "error")
                return redirect(url_for("auth.two_factor_setup"))
            
            current_user.two_factor_enabled = False
            current_user.two_factor_secret = None
            current_user.two_factor_backup_codes = None
            from app.extensions import db
            db.session.commit()
            auth_logger.info(f"2FA disabled for user: {current_user.username}")
            flash("Two-factor authentication disabled.", "success")
            return redirect(url_for("auth.two_factor_setup"))
    
    # GET request - show setup page
    qr_code_data = None
    secret = None
    backup_codes = None
    
    if current_user.two_factor_secret:
        secret = current_user.two_factor_secret
        # Generate QR code
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=current_user.email,
            issuer_name="TT Shop Gen"
        )
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_code_data = base64.b64encode(buffer.getvalue()).decode()
        
        if not current_user.two_factor_enabled:
            backup_codes = current_user.get_backup_codes()
    
    return render_template("2fa_setup.html", 
                         qr_code_data=qr_code_data, 
                         secret=secret,
                         backup_codes=backup_codes,
                         two_factor_enabled=current_user.two_factor_enabled)


def handle_2fa_verify():
    """Handle 2FA verification during login"""
    if request.method != "POST":
        return redirect(url_for("auth.login"))
    
    code = request.form.get("code")
    user_id = session.get("2fa_user_id")
    
    if not code or not user_id:
        flash("Verification code is required!", "warning")
        return redirect(url_for("auth.login"))
    
    user = User.query.get(user_id)
    if not user:
        flash("Session expired. Please log in again.", "error")
        session.pop("2fa_user_id", None)
        return redirect(url_for("auth.login"))
    
    # Verify TOTP code
    if user.two_factor_secret:
        totp = pyotp.TOTP(user.two_factor_secret)
        if totp.verify(code, valid_window=1):
            # Successful verification
            session.pop("2fa_user_id", None)
            from flask_login import login_user
            login_user(user)
            user.update_activity()
            auth_logger.info(f"2FA verified successfully for user: {user.username}")
            flash("Logged in successfully.", "success")
            target = "gm.gm_home" if user.role == "GM" else "player.player_home"
            return redirect(url_for(target))
    
    # Check backup codes
    if user.use_backup_code(code):
        session.pop("2fa_user_id", None)
        from flask_login import login_user
        login_user(user)
        user.update_activity()
        auth_logger.info(f"2FA verified with backup code for user: {user.username}")
        flash("Logged in successfully using backup code.", "success")
        target = "gm.gm_home" if user.role == "GM" else "player.player_home"
        return redirect(url_for(target))
    
    flash("Invalid verification code!", "error")
    return render_template("2fa_verify.html", user_id=user_id)


def handle_2fa_disable():
    """Handle 2FA disable request"""
    if request.method != "POST":
        return redirect(url_for("auth.two_factor_setup"))
    
    password = request.form.get("password")
    if not password or not current_user.check_password(password):
        flash("Incorrect password!", "error")
        return redirect(url_for("auth.two_factor_setup"))
    
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    current_user.two_factor_backup_codes = None
    from app.extensions import db
    db.session.commit()
    auth_logger.info(f"2FA disabled for user: {current_user.username}")
    flash("Two-factor authentication disabled.", "success")
    return redirect(url_for("auth.two_factor_setup"))

