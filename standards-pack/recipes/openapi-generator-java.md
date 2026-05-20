# Generating a Java client with OpenAPI Generator

[OpenAPI Generator](https://openapi-generator.tech/) is the canonical
tooling for producing a Java client from the SBS OpenAPI 3.1 spec.
This recipe pins the generator to **`v7.10.0`** and documents the
"wrap, never edit generated files" pattern that the regulator-domain
comparator set converges on.

See [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
for why Java integrators use a generator (rather than a hand-
maintained SBS helper) plus the [reference webhook verification
snippet](webhook-verification-java.md) for the signing primitive.

## Pinned generator version

```
openapitools/openapi-generator-cli:v7.10.0
```

The version is pinned because generator outputs are NOT stable across
versions — minor releases reshuffle naming conventions, change
nullability handling, and occasionally adjust default annotation
sets. Pinning protects your existing wrapper code from churn.

## Generate the client

From the root of the pack (extracted from the tarball):

```bash
docker run --rm -v "${PWD}:/local" \
  openapitools/openapi-generator-cli:v7.10.0 generate \
    -i /local/openapi/sbs-complaints-v0.1.yaml \
    -g java \
    -o /local/generated/java-client \
    --additional-properties=library=okhttp-gson,artifactId=sbs-suptech-client,artifactVersion=0.1.0,groupId=pe.gob.sbs.sandbox.client,invokerPackage=pe.gob.sbs.sandbox.client.invoker,apiPackage=pe.gob.sbs.sandbox.client.api,modelPackage=pe.gob.sbs.sandbox.client.model,dateLibrary=java8
```

The `additional-properties` block names the package conventions; pick
values that match your project's existing package namespace.

## "Wrap, never edit" pattern

Generated client code is a tree of `*Api.java` and `*Model.java`
files. The first impulse on first integration is to edit them —
rename methods, add nullability annotations, hand-fix the rough
edges. **Don't do this.** The next generator run overwrites your
edits and produces a merge conflict you cannot resolve cleanly.

The community-converged pattern is:

1. Run the generator to a fixed output directory
   (`generated/java-client/`).
2. Commit the generated output as-is (or recompute it on every build
   — either is fine, but pick one).
3. Write a thin wrapper module in your own package that:
   - Calls the generated `*Api` classes for the request layer.
   - Adapts the generated `*Model` classes to your domain model.
   - Implements webhook signature verification using the
     [Java verification snippet](webhook-verification-java.md) (this
     is NOT in the generator's output — it is yours).

When SBS publishes a new spec version, you re-run the generator and
your wrapper module continues to compile (modulo wire-contract
changes the spec signals via semver).

## Java-specific gotchas

- **Nullability annotations.** The `java` generator emits
  `@javax.annotation.Nullable` and `@javax.annotation.Nonnull` on
  fields whose schema declares `nullable: true`. If your project
  uses JSR-305 or Checker Framework annotations, configure the
  generator's `--additional-properties=annotationLibrary=...` (the
  full list is in the OpenAPI Generator docs).

- **Date handling.** Use `--additional-properties=dateLibrary=java8`
  to emit `java.time.LocalDate` and `java.time.OffsetDateTime`. The
  default (`threetenbp`) is for pre-Java-8 environments and is not
  relevant for the SBS sandbox's Java 17 audience.

- **OAuth scopes.** The generator emits an `oauth2_client_credentials`
  authentication wrapper. Configure your client's token endpoint
  per [ADR 0032](../../docs/adr/0032-oauth-client-credentials.md).

- **mTLS configuration.** The OkHttp invoker accepts a custom
  `SSLContext`. Load your institution's regulator-issued client
  cert + key into a `KeyStore`, build an `SSLContext` from it, and
  pass it to the `ApiClient`. The generated code does NOT manage the
  TLS layer for you — that is the integrator's responsibility.

## Upgrade path

When OpenAPI Generator releases v7.11.0+ and you decide to upgrade:

1. Bump the pinned version in the docker invocation above.
2. Re-run the generator.
3. Diff the generated output against the previous run. The most
   common breakage is renamed methods (e.g.
   `apiClient.getApiClient()` → `apiClient.getClient()`).
4. Update your wrapper module's call sites to match.
5. Run your existing test suite to confirm wire behaviour is
   unchanged.

The "wrap, never edit" pattern keeps this upgrade step finite — the
generated code can change freely, your wrapper is the contract.
