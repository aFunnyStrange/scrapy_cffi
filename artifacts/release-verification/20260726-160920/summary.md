# scrapy-cffi verification

Overall: **PASS**

| Scope | Phase | Result | Seconds | Log |
| --- | --- | --- | ---: | --- |
| framework | pytest | PASS | 5.20 | pytest.log |
| memory | generate/import | PASS | 0.78 | memory/generated-project.log |
| memory | plan-single | PASS | 0.34 | memory/plan-single.log |
| redis | generate/import | PASS | 0.64 | redis/generated-project.log |
| redis | plan-single | PASS | 0.34 | redis/plan-single.log |
| redis | plan-sentinel | PASS | 0.33 | redis/plan-sentinel.log |
| redis | plan-cluster | PASS | 0.30 | redis/plan-cluster.log |
| rabbitmq | generate/import | PASS | 0.86 | rabbitmq/generated-project.log |
| rabbitmq | plan-single | PASS | 0.39 | rabbitmq/plan-single.log |
| rabbitmq | plan-sentinel | PASS | 0.36 | rabbitmq/plan-sentinel.log |
| rabbitmq | plan-cluster | PASS | 0.36 | rabbitmq/plan-cluster.log |
| kafka | generate/import | PASS | 0.72 | kafka/generated-project.log |
| kafka | plan-single | PASS | 0.30 | kafka/plan-single.log |
| kafka | plan-sentinel | PASS | 0.30 | kafka/plan-sentinel.log |
| kafka | plan-cluster | PASS | 0.28 | kafka/plan-cluster.log |
