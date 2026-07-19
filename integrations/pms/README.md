# PMS Integrations

`cliniko/` will contain the live adapter. `mock/` will implement the identical contract with deterministic failure injection. Application services must depend on the gateway contract, never on either provider directly.
