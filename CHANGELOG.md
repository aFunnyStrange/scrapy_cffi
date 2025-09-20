# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
1.新增 redis 爬虫支持 redis 哨兵，集群模式 (70%)
2.抽离调度器与去重器 (100%)
3.扩展，爬虫的 hooks 支持所有数据库/mq (0%)
4.新增 mq 管理，rabbitmq 实现队列通信 (50%)
5.日志管理队列 kafka，同时兼容原来的 logger.xx()形式 (30%)
6.session_end 应当抽离一个对象，而不应该污染数据，需要兼容 websocket 模式 (0%)

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
