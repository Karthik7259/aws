import nodemailer from "nodemailer";

const [, , toEmail, fullNameArg, departmentArg] = process.argv;

if (!toEmail || !fullNameArg || !departmentArg) {
  console.error("Usage: node scripts/send-admin-access-email.mjs <toEmail> <fullName> <department>");
  process.exit(2);
}

const host = process.env.SMTP_HOST?.trim();
const port = Number(process.env.SMTP_PORT || "587");
const secure = String(process.env.SMTP_SECURE || "false").toLowerCase() === "true";
const user = process.env.SMTP_USER?.trim();
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

const fullName = fullNameArg.trim();
const department = departmentArg.trim();

const html = `
  <div style="font-family: Arial, sans-serif; line-height: 1.5; color: #222;">
    <h2 style="margin: 0 0 12px;">Access Approved - Grievance Mitra</h2>
    <p>Hello ${fullName},</p>
    <p>Your department admin profile for <strong>${department}</strong> has been approved by the Super Admin.</p>
    <p>You can now login and access the dashboard.</p>
    <p style="margin-top: 16px;">Regards,<br/>Grievance Mitra Team</p>
  </div>
`;

try {
  await transporter.sendMail({
    from,
    to: toEmail,
    subject: "Your Grievance Mitra dashboard access is approved",
    text: `Hello ${fullName}, your department admin access for ${department} is approved. You can now login and access the dashboard.`,
    html,
  });
  process.stdout.write("Access email sent");
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
