---
name: coding-agent-vpn-blocked-domains
description: When a domain blocks or refuses a request, check whether the traffic went through a VPN and suggest the matching fix to the user. Blocked while on the VPN, as with a 403, a bot or CAPTCHA challenge, "access denied" or a reset connection, suggest excluding the domain from the VPN through its split tunnelling. Blocked while off the VPN, as with a geo-block, HTTP 451, "not available in your region" or an ISP block page, suggest connecting the VPN. Use whenever a fetch, curl, package download, git clone, API call or browser page fails in a way that looks like the site refusing the connection rather than a bug, both in main agents and subagents.
---

# VPN and blocked domains

_A site that refuses a request often refuses where it comes from, not what it asks. Check whether the request went through the VPN, then suggest the change to the user: exclude the domain from the VPN, or connect it._

## Is the domain blocked?

Signs the site refused the connection, rather than the request being wrong:

- **Refusals:** HTTP 403 or 429 on a request that should work, an "Access denied" or "Request blocked" page, a Cloudflare, Akamai or other bot challenge ("Just a moment…", "Verify you are human"), or a connection reset or TLS failure on one domain only.
- **Geo-blocks:** HTTP 451, "not available in your country or region", or a page from an ISP or network naming a block.

A 404, a 401 or a malformed request is not a block.

## Is the traffic on the VPN?

On macOS, look up the interface that carries traffic to the domain's address:

```bash
route -n get "$(dig +short example.com | tail -1)" | awk '/interface/ {print $2}'
scutil --nc list | grep Connected
```

A `utun` interface means a tunnel carries it. `scutil --nc list` names the VPNs connected. A tunnel that carries only a private network, such as Tailscale with no exit node, doesn't route public addresses, so it doesn't count.

## What to suggest

| Blocked while | Suggest                                                                                                            |
| ------------- | ------------------------------------------------------------------------------------------------------------------ |
| On the VPN    | Exclude the domain from the VPN, in the VPN app's split-tunnelling or exclusion list, then retry.                  |
| Off the VPN   | Connect the VPN, choosing a location where the site serves, then retry; or, if it's always needed, route it there. |

- **Name the domain** to exclude or route, and the VPN app the check found.
- **Suggest, never change it:** VPN settings are the user's network and security settings. Never edit, disconnect or connect the VPN yourself.
- **Never get round a challenge:** don't solve a CAPTCHA or bot check, and don't retry in a loop or switch user agents to slip past a block. Say what blocked the request and stop.
- **Go on with other work** while the user decides, when there is any.

## Your preferences

!`cat "${CLAUDE_SKILL_DIR}/../coding-agent-vpn-blocked-domains.preferences.md" "${CLAUDE_PROJECT_DIR}/.agents/skills/coding-agent-vpn-blocked-domains.preferences.md" 2>/dev/null || true`

If your agent doesn't run the line above, read these files yourself if they
exist: `coding-agent-vpn-blocked-domains.preferences.md` next to this skill's folder, then
`.agents/skills/coding-agent-vpn-blocked-domains.preferences.md` in the project. A project's
file overrides the user's, and the user's overrides this skill's defaults.

A preferences file can name the VPN app and where its exclusion list is, and the domains already known to need the VPN or to need excluding.

## Related skills

When one of these applies and it's in your skill listing, load it
without asking. If it isn't in your listing, tell the user which skill is
missing and ask whether to install it from the same collection this skill
came from; don't apply it from memory.

- `coding-agent-questions-as-first-class-prompts`: asks the user whether to exclude the domain or connect the VPN through the structured-question tool.
- `coding-agent-skill-references`: where this skill's preferences files live and who writes them.
