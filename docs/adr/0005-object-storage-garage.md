# ADR-0005: S3 API as the storage contract; Garage for self-hosted deployments

- **Status:** accepted (pending PoC V6)
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
