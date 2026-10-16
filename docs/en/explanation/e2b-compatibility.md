# E2B behavior and Alibaba backend capabilities

The standard public API follows the fixed Alibaba-supported E2B versions. `Sandbox` is synchronous, `AsyncSandbox` asynchronous, and `agent_sandbox.code_interpreter` supplies the interpreter client. Project provider/server/declarative extensions use `ProviderSandbox`.

The project owns an attributed MIT source port and its protocol transport; it does not install or invoke the E2B runtime packages. A matching method name is insufficient: pagination, return models, exceptions, streaming and PTY behavior are part of the contract.

Read the [migration contract](../guide/migrate-from-e2b.md) for exact imports, configuration, conditional features and unsupported backend operations. Imported types do not imply that Alibaba enables their service endpoints.
