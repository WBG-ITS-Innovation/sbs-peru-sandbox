# Go webhook verification — reference snippet

A working reference implementation of SBS webhook signature
verification in Go. ~30 lines of standard library (`crypto/hmac`,
`crypto/sha256`, `encoding/base64`, `encoding/hex`) — no third-party
dependencies.

See [ADR 0035](../../docs/adr/0035-outbound-webhook-signing-contract.md)
for the contract and [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
for why Go gets a snippet (not a full helper).

A CI test extracts the code block below verbatim and runs it
against a fixture signed payload that the server-side outbound
signer produced.

## The snippet

```go
// sbs_webhook_verifier.go — reference implementation for SBS webhook
// signature verification. Standard library only.
//
// Build: go build -o sbs_webhook_verifier sbs_webhook_verifier.go
// Run:   ./sbs_webhook_verifier <secret> <timestamp> <body> \
//                                <institution_id> <signature-header> \
//                                <method> <callback-path>

package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"os"
	"strings"
)

const (
	algorithmPrefix = "hmac-sha256-v1="
	keyIDSandboxV1  = "sandbox-v1"
)

func verify(secret []byte, keyID, timestamp string, rawBody []byte,
	signatureHeader, method, callbackPath, institutionID string) error {
	if keyID != keyIDSandboxV1 {
		return fmt.Errorf("KeyIdUnknown: %s", keyID)
	}
	if !strings.HasPrefix(signatureHeader, algorithmPrefix) {
		return fmt.Errorf("SignatureInvalid: missing prefix")
	}
	sha := sha256.Sum256(rawBody)
	canonical := fmt.Sprintf("%s\n%s\n%s\n%s\n%s",
		strings.ToUpper(method), callbackPath, timestamp,
		hex.EncodeToString(sha[:]), institutionID)
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(canonical))
	expected := algorithmPrefix + base64.StdEncoding.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(expected), []byte(signatureHeader)) {
		return fmt.Errorf("SignatureInvalid: mismatch")
	}
	return nil
}

func main() {
	if len(os.Args) != 8 {
		fmt.Fprintln(os.Stderr, "usage: ... <secret> <ts> <body> <inst> <sig> <method> <path>")
		os.Exit(2)
	}
	if err := verify([]byte(os.Args[1]), keyIDSandboxV1, os.Args[2],
		[]byte(os.Args[3]), os.Args[5], os.Args[6], os.Args[7], os.Args[4]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println("VERIFY_OK")
}
```

## Critical: replay protection is your responsibility

SBS does NOT enforce replay protection on the receiving institution's
behalf — the server is the sender. Your receiver must track
recently-seen `(timestamp, signature)` pairs within the 5-minute
skew window and reject duplicates.

## Timestamp skew

The skew tolerance is ±300 seconds (5 minutes either direction).
Implement the check after parsing `X-SBS-Timestamp` as an RFC 3339
UTC instant. The snippet above omits the skew check for brevity; in
production, reject timestamps outside the window.

## Known issue with the OpenAPI Generator Go template

If you generate the API client from the OpenAPI spec via OpenAPI
Generator (recipe at `openapi-generator-go.md`), the Go template's
`oneOf` / `anyOf` / discriminator handling is incomplete as of
generator v7.10.0 and may produce code that does not compile for
union-typed response payloads. The standard workaround documented
in the Open Banking UK community is to drop the affected schemas to
`type: object` in the generator input or hand-edit the affected files
post-generation. The verification snippet above does not depend on
generated code and is unaffected.
