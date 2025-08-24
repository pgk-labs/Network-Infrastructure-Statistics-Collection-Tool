# email_sender.py

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Email server settings
SMTP_SERVER = ""  # Replace with your SMTP server address
SMTP_PORT =  25 # Replace with your SMTP server port (usually 587 for TLS)

# Email account credentials
SMTP_USERNAME = ""
# SMTP_PASSWORD = ""

# Recipient and CC email addresses
TO_EMAIL = ""
CC_EMAILS = [""]  # Add any CC emails here

# Email subject
EMAIL_SUBJECT = "PyATS overview"

def send_email(email_body):
 # Create a MIMEText object for the email body
    message = MIMEMultipart()
    message.attach(MIMEText(email_body, "plain"))

    # Add recipient and CC addresses to the email
    message["To"] = TO_EMAIL
    message["Cc"] = ", ".join(CC_EMAILS)

    # Set the email subject
    message["Subject"] = EMAIL_SUBJECT

    # Set the email sender (From) address
    message["From"] = ""

    try:
        # Connect to the SMTP server on port 25
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        # server.starttls()  # Start TLS encryption if needed
        # server.login(SMTP_USERNAME, SMTP_PASSWORD)  # Log in if required

        # Send the email
        server.sendmail(message["From"], [TO_EMAIL] + CC_EMAILS, message.as_string())
        #server.sendmail(message["From"], [TO_EMAIL], message.as_string())
        # Close the SMTP server connection
        server.quit()

        print("Email notification has been sent.")
    except Exception as e:
        print(f"Error sending email: {str(e)}")

