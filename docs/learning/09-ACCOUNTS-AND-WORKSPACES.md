# Phase 2: accounts and workspaces

The account proves who a person is. A membership grants that person a role in one workspace. Logging in does not grant access to every workspace: FastAPI checks membership on each workspace request. Removing a membership therefore blocks subsequent workspace requests without deleting the account or its other workspaces.

## How to try it

1. Open Settings in your workspace and request a verification email. Existing accounts start unverified; no email ownership is assumed.
2. Open the development inbox at http://localhost:8025 and follow the verification link. Refresh Settings to see the verified status.
3. Invite an email address as editor, viewer, or (owner only) administrator. The email contains a seven-day invitation.
4. The recipient registers or signs in using that address, verifies it, then opens the invitation and chooses Continue. Sign-in/register links open another tab so the invitation remains available.
5. Change a member's role or remove access from Settings. Promote another owner before demoting the final owner. Owners cannot be removed directly.
6. Use Forgot your password from sign-in to request a one-hour recovery link. Successful reset revokes every existing session; the user signs in again with the new password.

## Decisions and boundaries

- Tokens are random bearer secrets; only their hashes are stored in token/invitation tables. The raw links occur in encrypted outbox payloads so the mail worker can deliver them. Links use URL fragments, which are not sent in HTTP requests or referrers. Single-use consumption, expiry, role changes and token replacement are checked by the server.
- Email verification lasts 24 hours per link. Reissuing verification or password recovery invalidates older links. Recovery responses do not disclose whether an account exists. All mutations require the existing origin and CSRF checks, and sensitive requests are rate limited.
- PostgreSQL locks serialize token consumption and workspace membership changes. Database uniqueness prevents duplicate memberships. Accepting an invitation never overwrites an existing member's role. An inviter who lost administration rights cannot grant new membership through an old invitation.
- Owners can manage all roles. Admins manage editors/viewers and workspace details; they cannot grant themselves ownership or manage another admin. At least one owner remains. Fine resource permissions and approval workflows belong to phase 13.
- Mail is queued in the same transaction as its token or invitation. SMTP outages do not roll back registration. A separate maintenance pass retries up to five times with exponential backoff; resend creates a fresh token and mail job. SMTP acceptance is delivery to the server, not proof that the person read the email. A crash after SMTP accepts a message can duplicate that email, but cannot redeem a token twice.
- Password reset/change revokes all device sessions. Email verification does not gate existing local agent work; it gates inviting and joining teams. MFA, SSO, subscriptions and enterprise provisioning are later scope.

## Development versus public email

Compose runs Mailpit with its inbox bound only to localhost:8025. No public email is sent by default. Set SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_STARTTLS and MAIL_FROM for a real provider, plus PUBLIC_ORIGIN and secure cookies/HTTPS. Authenticated SMTP requires STARTTLS. Keep the password in deployment secret storage. Mailpit is a development capture service, not the production sender.

## Verification

The PostgreSQL/Redis suite covers token expiry/reuse/purpose, generic recovery responses, old-password denial, session revocation, encrypted mail storage, delivery retry, real SMTP acceptance by Mailpit, invitation identity/replacement/revocation, cross-workspace isolation, member removal, viewer write denial, admin escalation denial and ownership transfer. The complete frontend production build checks the new routes and server/client boundaries. No real mailbox credentials are needed for local testing.
