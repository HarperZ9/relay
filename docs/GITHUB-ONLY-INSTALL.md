# GitHub-only install guidance

Relay's Python package metadata currently uses the distribution name
`relay-agent`, but the public PyPI namespace with that name is not the HarperZ9
Relay distribution. Do not run `pip install relay-agent` and do not document it
as a Relay install path.

Use one of these GitHub-pinned paths after the release owner has committed and
published the release.

## Source pin

Replace `<accepted-commit>` with the reviewed commit SHA from
`https://github.com/HarperZ9/relay`.

```bash
python -m pip install "relay-agent @ git+https://github.com/HarperZ9/relay.git@<accepted-commit>"
```

This still installs a package whose local metadata name is `relay-agent`, but the
source is pinned to HarperZ9 GitHub. The commit SHA is the authority; omitting it
turns the install into a moving target.

## Release wheel

After the GitHub Release exists, download the wheel and SHA-256 receipt from the
release page. Example 0.2.3 release asset names:

```text
tag: v0.2.3
wheel: relay_agent-0.2.3-py3-none-any.whl
sdist: relay_agent-0.2.3.tar.gz
sha256: <release-sha256-from-SHA256SUMS.txt>
url: https://github.com/HarperZ9/relay/releases/download/v0.2.3/<asset-name>
```

Verify the hash before installing. Do not continue to `pip install` if the wheel has no checksum line or the computed hash differs. Example in PowerShell:

```powershell
& {
  $ErrorActionPreference = "Stop"
  $wheel = "relay_agent-0.2.3-py3-none-any.whl"
  $pattern = "^[0-9a-fA-F]{64}\s+$([regex]::Escape($wheel))$"
  $matches = @(Select-String -LiteralPath ".\SHA256SUMS.txt" -Pattern $pattern)
  if ($matches.Count -ne 1) { throw "expected exactly one SHA256SUMS entry for $wheel; found $($matches.Count)" }
  $expected = ($matches[0].Line -split "\s+")[0].ToLowerInvariant()
  $actual = (Get-FileHash -LiteralPath ".\$wheel" -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected) { throw "sha256 mismatch for $wheel" }
  python -m pip install --no-index ".\$wheel"
}
```

This path does not query PyPI. If a future release moves to a new verified
package namespace, update this page and the release notes before publishing.
