# CDN requirements

The package origin must return the following headers:

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, HEAD, OPTIONS
Cross-Origin-Resource-Policy: cross-origin
X-Content-Type-Options: nosniff
```

Package objects are content-addressed and may use immutable caching. Repository metadata must be revalidated so APT updates become visible without waiting for an old CDN TTL.
