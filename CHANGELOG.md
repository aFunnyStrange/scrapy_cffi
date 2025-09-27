# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
1.Redis support single、sentinel、cluster
2.Extract dupefilter from the scheduler
3.Extension support databases/mq
4.Mq module，rabbitmq (70%, aio-pika rpc -> Channel closed by RPC timeout.)
5.Mq module，kafka for log
6.Session_end must be an independent object
7.Command support rabbitmq_spider
8.Full bloom dupefilter
9.C Extensions support
10.SettingsInfo PROJECT_NAME -> QUEUE_NAME

---

## [0.1.6] - 2025-09-07
### Added
- Spider hooks get_session_cookies
- Email send util
- StatisticsExtension

## Fixed
- Request Interceptor behavior bug (return a Response)

---

## [0.1.5] - 2025-09-06
### Added
- Initial PyPI release
- CLI change `scrapy-cffi`
- Have a try GitHub Actions workflow for publishing
- Enhance JSON parsing
- Optimize some project structures

## Fixed
- Response selector parsing behavior bug

---
