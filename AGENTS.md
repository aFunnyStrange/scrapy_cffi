# Repository verification contract

Every framework or generated-template change must finish with the complete
verification matrix described in `docs/TESTING.md`. A focused pytest run is
only an intermediate check; it never replaces the final matrix.

The release gate must exercise the real generated-project path used by
`scrapy-cffi demo` and `scrapy-cffi startproject`, not only framework unit
tests. Validate Memory, Redis, RabbitMQ, and Kafka on both Windows and WSL
Ubuntu. Finite spiders must exit naturally. Continuous spiders must remain
subscribed after their current work is complete and stop only after an explicit
shutdown signal.

In `run_all_spiders`, a completed finite Engine must not stop a sibling
continuous Engine. Preserve each spider's scheduler semantics by default: a
normal `Spider` keeps the in-memory `Scheduler` when Redis/RabbitMQ/Kafka
spiders are also loaded. Only an explicit global `settings.SCHEDULER` applies
one scheduler class to every spider.

Framework lifecycle decisions must be event-driven. Never infer producer
completion, crawler completion, WebSocket closure, or scheduler completion from
sleep duration, timeout expiry, repeated empty-queue reads, or a configurable
number of polling loops. Timeouts are allowed only as external test safety
bounds or transport retry bounds; they are not business or lifecycle signals.
