# Generating a Go client with OpenAPI Generator

This recipe uses the `go` generator. Pinned to OpenAPI Generator
**`v7.10.0`**. The Go generator has a known issue with `oneOf` /
`anyOf` / discriminator unions — see the **Known issue** section
below before you generate.

See [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
for why Go integrators use a generator. For webhook verification,
use the [Go verification snippet](webhook-verification-go.md) — the
generator does NOT produce that for you, and it must not be
auto-generated from the spec.

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
    -g go \
    -o /local/generated/go-client \
    --additional-properties=packageName=sbsclient,packageVersion=0.1.0,withGoMod=true,generateInterfaces=true
```

## Known issue with oneOf / anyOf / discriminator unions

The Go template's union-type handling is **incomplete** in v7.10.0
and the released v7.11.0. The generated code for any schema that uses
`oneOf`, `anyOf`, or a discriminator on a polymorphic response often
**does not compile** — the generator emits type signatures it cannot
back with marshallers.

The SBS spec uses unions for: the `ProblemDetail` extensibility (some
4xx and 5xx responses extend `ProblemDetail` with response-specific
`errors[]` shapes). If you hit a compile error on the generated Go
client, the workaround documented in the Open Banking UK community is:

1. **Option A — drop unions in the generator input.** Make a copy of
   the OpenAPI spec, replace the affected `oneOf`/`anyOf` schemas with
   `type: object`, re-run the generator. You lose discriminator
   strict-typing at the wire level but your client compiles.
2. **Option B — hand-edit the generator output.** Identify the
   broken `*Marshal.go` files and write the marshallers by hand. Pin
   the spec version so future regenerations do not clobber your work,
   or use a generator template override.
3. **Option C — wait for the upstream fix.** OpenAPI Generator's
   issue tracker has multiple open tickets on this; the long-term
   answer is template improvements. Until then, options A and B are
   the practical workarounds.

The [Go verification snippet](webhook-verification-go.md) does NOT
depend on the generated client; webhook verification is independent
of the request-layer client.

## "Wrap, never edit" pattern

Same as Java and C#: generated code is `api_*.go` + `model_*.go`,
your wrapper module is in a separate Go package and calls into the
generated client. When SBS publishes a new spec version, you re-run
the generator and your wrapper continues to compile.

## Go-specific gotchas

- **`withGoMod=true`** emits a `go.mod` in the output. Pin module
  paths via your own `go.mod` `replace` directive if you vendor the
  generated client into your repository.

- **`generateInterfaces=true`** produces `*Api` interfaces alongside
  the concrete implementations. Use the interfaces in your wrapper
  module's call sites so you can mock them in tests without
  depending on the generated HTTP client.

- **Context-aware methods.** The Go generator emits
  `func (a *FooApi) BarExecute(r ApiBarRequest) (*ResponseBody,
  *http.Response, error)` and a separate `Bar(ctx, ...) ApiBarRequest`
  builder. Pass `context.Context` for cancellation and deadlines —
  the default no-context invocation is convenient for prototyping but
  unsafe in production where deadlines matter.

- **mTLS configuration.** The generated client's `Configuration`
  struct accepts an `HTTPClient *http.Client`. Build an
  `http.Client` with a custom `Transport` that loads your
  institution's regulator-issued cert via `tls.LoadX509KeyPair`,
  then pass the client to the generated `Configuration`.

## Upgrade path

Same as Java and C#:

1. Bump the pinned generator version.
2. Re-run the generator.
3. Diff the generated output.
4. Update your wrapper module's call sites.
5. Run your existing test suite to verify wire behaviour.
6. Re-check the **Known issue** section above — track whether the
   union-type handling has improved in the new version.
