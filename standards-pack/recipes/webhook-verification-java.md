# Java webhook verification — reference snippet

A working reference implementation of SBS webhook signature
verification in Java. Adapt it to your host framework (Spring,
Jakarta EE, Helidon, etc.); the verification primitive itself is
~30 lines of `javax.crypto` and is the same regardless of the
surrounding stack.

See [ADR 0035](../../docs/adr/0035-outbound-webhook-signing-contract.md)
for the contract and [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
for why Java gets a snippet (not a full helper).

A CI test extracts the code block below verbatim and runs it
against a fixture signed payload that the server-side outbound
signer produced.

## The snippet

```java
// SbsWebhookVerifier.java — reference implementation for SBS webhook
// signature verification. Pure JDK; no third-party dependencies.
//
// Compile:  javac SbsWebhookVerifier.java
// Run:      java SbsWebhookVerifier <secret> <timestamp> <body> \
//                                    <institution_id> <signature-header> \
//                                    <method> <callback-path>

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SbsWebhookVerifier {
    public static final String ALGORITHM_PREFIX = "hmac-sha256-v1=";
    public static final String KEY_ID_SANDBOX_V1 = "sandbox-v1";

    public static void verify(byte[] secret, String keyId, String timestamp,
                              byte[] rawBody, String signatureHeader,
                              String method, String callbackPath,
                              String institutionId)
            throws NoSuchAlgorithmException {
        if (!KEY_ID_SANDBOX_V1.equals(keyId))
            throw new RuntimeException("KeyIdUnknown: " + keyId);
        if (!signatureHeader.startsWith(ALGORITHM_PREFIX))
            throw new RuntimeException("SignatureInvalid: missing prefix");
        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        String bodyHex = HexFormat.of().formatHex(sha.digest(rawBody));
        String canonical = method.toUpperCase() + "\n" + callbackPath + "\n"
                + timestamp + "\n" + bodyHex + "\n" + institutionId;
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] expectedMac = mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
            String expectedHeader = ALGORITHM_PREFIX + Base64.getEncoder().encodeToString(expectedMac);
            if (!MessageDigest.isEqual(expectedHeader.getBytes(StandardCharsets.UTF_8),
                                       signatureHeader.getBytes(StandardCharsets.UTF_8)))
                throw new RuntimeException("SignatureInvalid: mismatch");
        } catch (Exception exc) {
            throw new RuntimeException("verify failed: " + exc.getMessage(), exc);
        }
    }

    // CLI for the CI fixture: argv carries the canonical-request
    // inputs plus the presented signature header.
    public static void main(String[] argv) throws Exception {
        byte[] secret = argv[0].getBytes(StandardCharsets.UTF_8);
        String timestamp = argv[1];
        byte[] rawBody = argv[2].getBytes(StandardCharsets.UTF_8);
        String institutionId = argv[3];
        String signatureHeader = argv[4];
        String method = argv[5];
        String callbackPath = argv[6];
        verify(secret, KEY_ID_SANDBOX_V1, timestamp, rawBody, signatureHeader,
               method, callbackPath, institutionId);
        System.out.println("VERIFY_OK");
    }
}
```

## Critical: replay protection is your responsibility

SBS does NOT enforce replay protection on the receiving institution's
behalf — the server is the sender, not the receiver. Your receiver
must track recently-seen `(timestamp, signature)` pairs within the
5-minute skew window and reject duplicates.

## Timestamp skew

The skew tolerance is ±300 seconds (5 minutes either direction).
Implement the check after parsing `X-SBS-Timestamp` as an RFC 3339
UTC instant. The snippet above omits the skew check for brevity; in
production, reject timestamps outside the window.

## Don't translate this by eye

The canonical request shape has five lines, joined by `\n` (LF, not
CRLF), UTF-8 encoded, with the body hashed as lowercase hex SHA-256.
Translating the Python helper to Java by eye is the dominant
verification-failure mode in implementer forums (Open Banking UK
documents this at length). Use this snippet as the starting point
and run the CI-tested fixture against it before you deploy.
