# ADR-0005: S3 API as the storage contract; Garage for self-hosted deployments

- **Status:** accepted (PoC V6 run at the storage layer on 2026-10-26, see below; the browser CORS leg and a 500 MB multipart upload are still open)
- **Date:** 2026-10-25
- **Plan reference:** §4.4

## Context
MinIO's community repository is archived and marked "no longer maintained" (2026-04), with users
directed to a paid product.

## Decision
The application speaks the S3 API only. Development and single-host production run Garage (AGPL-3.0,
unmodified service). SeaweedFS (Apache-2.0) or a managed S3-compatible bucket are drop-in
alternatives selected by configuration.

## Consequences
Presigned upload/download, multipart and bucket policy behaviour must be confirmed on Garage in PoC V6.

*PoC V6, run 2026-10-26 on Garage v2.5.0 (dev stack, `S3Storage` in a one-off container, throwaway
prefix removed at the end):* presigned PUT 200 and a PUT with another content type 403 (the signature
binds the type); `head` returns size and type; `get_bytes` identical; presigned GET 200 with
`Content-Type` and `Content-Disposition: inline; filename=` honoured; `copy` ok; anonymous GET on the
bucket 403 (no public policy; the portal reads through presigned links); 1003 small puts in 0.9 s;
`delete_prefix` removed 1005 keys in 0.2 s (two batches, the 1000-key limit crossed) and left 0; the
whole-bucket guard raises. Not run: a browser PUT through the public host (CORS on Garage is set by
`scripts/init-garage.sh`, unverified from a browser because the dev stack serves files from the `local`
backend), and a 500 MB multipart upload (the platform uploads with one presigned PUT, so multipart is
needed only if a file ever exceeds one PUT; Garage's limit is 5 GB per PUT).
