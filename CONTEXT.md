# aiognmi

An asynchronous gNMI client. This context covers the vocabulary the library uses to talk about gNMI
targets, paths, and the four gNMI RPCs it exposes.

## Language

**Target**:
A network device the client talks to, addressed as `host:port`. Also the name carried in a gNMI
`Path.target` field to disambiguate a device behind a collector.
_Avoid_: Device, host, node, server

**Path**:
A location in the target's data tree. Callers always express it as a string xpath
(`interfaces/interface[name=eth0]/state`); the protobuf `Path` message is an internal representation.
_Avoid_: XPath (as a distinct concept), pointer, selector

**Origin**:
The schema namespace a Path is resolved against, written as the `module:` prefix on an xpath. Defaults
to `openconfig` when the caller omits it.
_Avoid_: Module, namespace, prefix

**Notification**:
One timestamped batch of updates and deletes for a set of Paths, as returned by Get and Subscribe.
_Avoid_: Event, message, telemetry record, sample

## Subscribe

**Subscription**:
A single Path within a Subscribe request, together with the per-path options that govern when the
target sends Notifications for it.
_Avoid_: Watch, listener, stream (for the individual path)

**Mode**:
How the target delivers the whole subscription request: `stream` (target pushes indefinitely), `once`
(target sends one dump and closes), or `poll` (target sends a dump each time the client asks).
_Avoid_: Subscription mode, list mode, type

**Stream Mode**:
How the target decides when to send a Notification for one Subscription: `target_defined`, `on_change`,
or `sample`. Only meaningful under `mode="stream"`.
_Avoid_: Submode, subscription mode, sub-mode, per-path mode

**Sync Response**:
The target's signal that it has sent every value in the subscription at least once. Everything after it
is a genuine change or a fresh sample.
_Avoid_: Sync marker, initial dump complete, ready signal
