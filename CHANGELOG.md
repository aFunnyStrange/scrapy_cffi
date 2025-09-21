# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
1.Redis support single、sentinel、cluster (70%)
2.Extract dupefilter from the scheduler (100%)
3.Extension support databases/mq (100%)
4.Mq module，rabbitmq (70%, aio-pika rpc -> Channel closed by RPC timeout.)
5.Mq module，kafka for log (30%)
6.Session_end must be an independent object (0%)
7.Command support rabbitmq_spider (0%)

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
