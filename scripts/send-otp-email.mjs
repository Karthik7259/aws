import nodemailer from "nodemailer";

const [, , toEmail, otpCode] = process.argv;

if (!toEmail || !otpCode) {
  console.error("Usage: node scripts/send-otp-email.mjs <toEmail> <otpCode>");
  process.exit(2);
}

const host = process.env.SMTP_HOST?.trim();
const port = Number(process.env.SMTP_PORT || "587");
const secure = String(process.env.SMTP_SECURE || "false").toLowerCase() === "true";
const user = process.env.SMTP_USER?.trim();
// Gmail app passwords are often displayed with spaces; remove all whitespace safely.
const pass = (process.env.SMTP_PASS || "").replace(/\s+/g, "");
const from = (process.env.SMTP_FROM || user || "").trim();

if (!host || !user || !pass || !from) {
  console.error("SMTP environment is incomplete. Required: SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM");
  process.exit(3);
}

const transporter = nodemailer.createTransport({
  host,
  port,
  secure,
  auth: { user, pass },
});

const html = `
  <div style="font-family: Arial, sans-serif; line-height: 1.4; color: #222;">
    <h2 style="margin: 0 0 12px;">Grievance Mitra Admin OTP</h2>
    <p style="margin: 0 0 8px;">Use this code to verify your admin account:</p>
    <p style="font-size: 28px; font-weight: 700; letter-spacing: 4px; margin: 8px 0 12px;">${otpCode}</p>
    <p style="margin: 0;">This OTP expires in 10 minutes.</p>
  </div>
`;

try {
  await transporter.sendMail({
    from,
    to: toEmail,
    subject: "Your Grievance Mitra OTP",
    text: `Your OTP is ${otpCode}. It expires in 10 minutes.`,
    html,
  });
  process.stdout.write("OTP email sent");
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
