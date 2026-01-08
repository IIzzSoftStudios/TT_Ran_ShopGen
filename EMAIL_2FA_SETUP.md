# Email Registration, Account Recovery, and 2FA Setup Guide

## Overview
This document explains the email registration, account recovery, and two-factor authentication (2FA) features that have been added to your application.

## Features Implemented

### 1. Email Registration
- Users must provide an email address during registration
- Email verification is sent automatically upon registration
- Email verification can be required or optional (configurable)

### 2. Account Recovery via Email
- Password reset requests are sent via email (no more token display)
- Users can reset password using username or email
- Secure token-based reset links (expire in 1 hour)

### 3. Two-Factor Authentication (2FA)
- Optional 2FA using TOTP (Google Authenticator, Authy, etc.)
- QR code generation for easy setup
- Backup codes for account recovery
- Can be made required for all users (configurable)

## Installation Steps

### 1. Install Required Dependencies
```bash
pip install -r REQUIREMENTS_EMAIL_2FA.txt
```

Or install individually:
```bash
pip install Flask-Mail==0.9.1 pyotp==2.9.0 qrcode[pil]==7.4.2
```

### 2. Configure Email Settings
Edit `config.env` and update the email configuration:

```env
# Email Configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USE_SSL=False
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password_here
MAIL_DEFAULT_SENDER=your_email@gmail.com

# Application Settings
APP_NAME=TT Shop Gen
BASE_URL=http://localhost:5000

# Security Settings
REQUIRE_EMAIL_VERIFICATION=False  # Set to True to require email verification
REQUIRE_2FA=False  # Set to True to require 2FA for all users
```

### 3. Gmail Setup (if using Gmail)
1. Enable 2-Step Verification on your Google Account
2. Go to: Google Account > Security > 2-Step Verification > App Passwords
3. Generate an App Password for "Mail"
4. Use this App Password (not your regular password) in `MAIL_PASSWORD`

### 4. Run Database Migration
```bash
cd TT_Ran_ShopGen
flask db upgrade
```

This will add the following fields to the `user` table:
- `email` (unique, required)
- `email_verified` (boolean)
- `verification_token` and `verification_token_expires`
- `two_factor_enabled` (boolean)
- `two_factor_secret` (TOTP secret)
- `two_factor_backup_codes` (JSON array)

**Note:** Existing users will have placeholder emails (`username@placeholder.local`). They should update their email addresses.

## Usage

### For Users

#### Registration
1. Go to `/auth/register`
2. Fill in username, **email**, password, and role
3. Check your email for verification link
4. Click the verification link (if `REQUIRE_EMAIL_VERIFICATION=True`, you must verify before logging in)

#### Password Reset
1. Go to `/auth/forgot-password`
2. Enter your username or email
3. Check your email for reset link
4. Click the link and set a new password

#### Setting Up 2FA
1. Log in to your account
2. Navigate to `/auth/2fa/setup`
3. Scan the QR code with your authenticator app
4. Enter the 6-digit code to verify and enable 2FA
5. **Save your backup codes** in a safe place

#### Logging In with 2FA
1. Enter username and password
2. If 2FA is enabled, you'll be prompted for a 6-digit code
3. Enter the code from your authenticator app OR use a backup code

### For Administrators

#### Making Email Verification Required
Set in `config.env`:
```env
REQUIRE_EMAIL_VERIFICATION=True
```

#### Making 2FA Required for All Users
Set in `config.env`:
```env
REQUIRE_2FA=True
```

## Routes Added

- `/auth/register` - Registration (now requires email)
- `/auth/verify-email/<token>` - Email verification
- `/auth/resend-verification` - Resend verification email
- `/auth/forgot-password` - Request password reset (now sends email)
- `/auth/reset-password/<token>` - Reset password with token
- `/auth/2fa/setup` - Setup 2FA (requires login)
- `/auth/2fa/verify` - Verify 2FA code during login
- `/auth/2fa/disable` - Disable 2FA (requires login)

## Email Templates

Email templates are located in `app/templates/emails/`:
- `verify_email.html` - Email verification email
- `reset_password_email.html` - Password reset email
- `2fa_code.html` - 2FA code email (for email-based 2FA, if implemented)

You can customize these templates to match your application's branding.

## Troubleshooting

### Email Not Sending
1. Check your email credentials in `config.env`
2. For Gmail, ensure you're using an App Password, not your regular password
3. Check firewall/network settings (SMTP port 587)
4. Check application logs for error messages

### Migration Issues
If you have existing users without emails:
- The migration will assign placeholder emails
- Users should update their email addresses after migration
- You may need to manually update emails for existing users

### 2FA Not Working
1. Ensure `pyotp` and `qrcode[pil]` are installed
2. Check that the time on your server is synchronized (TOTP is time-sensitive)
3. Verify the QR code was scanned correctly
4. Try using a backup code if the authenticator app code doesn't work

## Security Notes

- Email verification tokens expire after 24 hours
- Password reset tokens expire after 1 hour
- 2FA backup codes are single-use
- All tokens use cryptographically secure random generation
- Email addresses are unique and validated

## Next Steps

1. Install dependencies: `pip install -r REQUIREMENTS_EMAIL_2FA.txt`
2. Configure email settings in `config.env`
3. Run migration: `flask db upgrade`
4. Test registration and email sending
5. Optionally add a link to `/auth/2fa/setup` in your user dashboard/navigation

