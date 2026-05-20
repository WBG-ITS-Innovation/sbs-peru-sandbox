# Generating a .NET client with OpenAPI Generator

This recipe uses the modern `csharp-netcore` generator (NOT the
older `csharp` generator — they produce materially different output;
this recipe documents the modern one). Pinned to OpenAPI Generator
**`v7.10.0`**.

See [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
for why .NET integrators use a generator. For webhook verification,
adapt the [Java verification snippet](webhook-verification-java.md)
into idiomatic C# — the canonical-request shape is identical; the
primitive is `System.Security.Cryptography.HMACSHA256` and constant-
time compare is `CryptographicOperations.FixedTimeEquals`.

## Pinned generator version

```
openapitools/openapi-generator-cli:v7.10.0
```

Pin the version. Generator outputs are not stable across versions.

## Generate the client

From the root of the pack (extracted from the tarball):

```bash
docker run --rm -v "${PWD}:/local" \
  openapitools/openapi-generator-cli:v7.10.0 generate \
    -i /local/openapi/sbs-complaints-v0.1.yaml \
    -g csharp-netcore \
    -o /local/generated/csharp-client \
    --additional-properties=packageName=Sbs.Suptech.Client,packageVersion=0.1.0,targetFramework=net8.0,netCoreProjectFile=true,validatable=true
```

The `targetFramework=net8.0` matches the .NET LTS at the time this
recipe was written; bump as appropriate.

## "Wrap, never edit" pattern

Same as the Java recipe: generated code is a `*Api.cs` + `*Model.cs`
tree, your wrapper module is in a separate namespace and calls into
the generated classes. When SBS publishes a new spec version, you
re-run the generator and your wrapper continues to compile.

The dominant integration pain point per Open Banking UK community
feedback is the "I edited the generated client and now my next
regeneration produces an unmergeable diff" failure. The wrapper
pattern prevents this.

## C#-specific gotchas

- **Namespace conventions.** `--additional-properties=packageName=...`
  controls the C# namespace. Pick a value that matches your
  project's existing namespace tree (e.g.
  `pe.gob.sbs.sandbox.client` → `Pe.Gob.Sbs.Sandbox.Client`).

- **Async/await.** The `csharp-netcore` generator emits async API
  methods by default (`Task<T>` returns). Pre-`csharp-netcore`
  generators emitted synchronous wrappers; if you see synchronous
  code, you are on the old generator and should migrate.

- **`validatable=true`** triggers data-annotation validation on
  generated models, so you can validate payloads via
  `Validator.TryValidateObject` before submitting. This is
  particularly useful for the batch-upload flow where catching a
  shape mismatch client-side is cheaper than a 422 round trip.

- **System.Text.Json vs Newtonsoft.Json.** The `csharp-netcore`
  generator uses `System.Text.Json` by default in modern emit
  modes; older versions used `Newtonsoft.Json`. If your project has
  a strong preference, configure the generator's
  `--additional-properties=useJsonSerializer=...` (consult the
  OpenAPI Generator docs for the current option name).

- **mTLS configuration.** The generated `ApiClient` uses
  `HttpClient` under the hood. Load your institution's regulator-
  issued client cert into an `X509Certificate2` and attach it to a
  `HttpClientHandler.ClientCertificates` instance, then pass the
  configured `HttpClient` to the `ApiClient`.

## Upgrade path

Same as Java:

1. Bump the pinned generator version.
2. Re-run the generator.
3. Diff the generated output.
4. Update your wrapper module's call sites.
5. Run your existing test suite to verify wire behaviour.
