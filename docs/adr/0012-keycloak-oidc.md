# ADR-0012 — OIDC authentication with Keycloak

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

The platform exposes sales data, serves several roles and must demonstrate enterprise-grade authentication, including between services.

## Decision

Keycloak with a `sentinel` realm imported from `infra/keycloak/`. The interface uses OIDC with PKCE; services use OAuth2 client credentials; `platform-api` is a JWT resource server. Roles `ADMIN`, `ANALYST`, `VIEWER`, `SERVICE`, and a `tenant_id` claim.

## Alternatives considered

- **Home-made signed JWT**: quick, but non-standard and fragile.
- **Auth0 or Cognito**: cloud dependency, contrary to the "everything local" goal.

## Consequences

- A standard recognized in industry, reusable as-is on Kubernetes.
- About 700 MB of extra RAM.
