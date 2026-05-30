import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

class EmailNotifier:
    def __init__(self, config):
        self.config = config
        self.server_addr = config['email'].get('smtp_server')
        self.port = config['email'].get('smtp_port', 587)
        self.sender = config['email'].get('sender_email')
        self.password = config['email'].get('password')
        self.recipient = config['email'].get('recipient_email')
        
    def send_alert(self, item):
        """
        Send email alert.
        """
        if not self.sender or not self.password or not self.recipient:
            logger.warning("Email not configured completely, skipping alert.")
            return

        score = item.get('score', 0)
        subject = f"[{score}/10] Investment Alert: {item.get('title')}"
        
        body = f"""
        <html>
          <body>
            <h2>{item.get('title')}</h2>
            <p><strong>Score:</strong> {score}/10</p>
            <p><strong>Source:</strong> {item.get('source')} ({item.get('published')})</p>
            <hr>
            <h3>Summary</h3>
            <p>{item.get('summary')}</p>
            <h3>Analysis</h3>
            <p>{item.get('reasoning')}</p>
            <hr>
            <p><a href="{item.get('link')}">Read Original Article</a></p>
          </body>
        </html>
        """
        
        msg = MIMEMultipart()
        msg['From'] = self.sender
        msg['To'] = self.recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        try:
            server = smtplib.SMTP(self.server_addr, self.port)
            server.starttls()
            server.login(self.sender, self.password)
            server.send_message(msg)
            server.quit()
            logger.info(f"Sent Email alert for: {item.get('title')}")
        except Exception as e:
            logger.error(f"Failed to send Email: {e}")

    def send_digest(self, items):
        """
        Send a digest email for multiple items.
        """
        if not items: return
        if not self.sender or not self.password or not self.recipient:
            logger.warning("Email not configured, skipping digest.")
            return

        subject = f"Investment Digest: {len(items)} Items Scored 3-8/10"
        
        # Build HTML Table
        rows = ""
        for item in items:
            score = item.get('score', 0)
            rows += f"""
            <tr style="border-bottom: 1px solid #ddd;">
                <td style="padding: 10px;"><strong>{score}</strong></td>
                <td style="padding: 10px;">
                    <a href="{item.get('link')}" style="text-decoration: none; color: #333; font-weight: bold;">{item.get('title')}</a>
                    <div style="font-size: 0.9em; color: #666; margin-top: 5px;">{item.get('summary')[:300]}...</div>
                </td>
                <td style="padding: 10px; font-size: 0.9em; white-space: nowrap;">{item.get('source')}</td>
            </tr>
            """
            
        body = f"""
        <html>
          <body>
            <h2>Investment Highlights (Score 3-8)</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background-color: #f8f9fa; text-align: left;">
                    <th style="padding: 10px;">Score</th>
                    <th style="padding: 10px;">Title & Summary</th>
                    <th style="padding: 10px;">Source</th>
                </tr>
                {rows}
            </table>
            <p>Total Items: {len(items)}</p>
          </body>
        </html>
        """
        
        msg = MIMEMultipart()
        msg['From'] = self.sender
        msg['To'] = self.recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        try:
            server = smtplib.SMTP(self.server_addr, self.port)
            server.starttls()
            server.login(self.sender, self.password)
            server.send_message(msg)
            server.quit()
            logger.info(f"Sent Digest Email with {len(items)} items.")
        except Exception as e:
            logger.error(f"Failed to send Digest Email: {e}")
