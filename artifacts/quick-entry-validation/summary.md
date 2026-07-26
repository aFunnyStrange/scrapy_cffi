# scrapy-cffi verification

Overall: **PASS**

| Scope | Phase | Result | Seconds | Log |
| --- | --- | --- | ---: | --- |
| framework | pytest | PASS | 4.55 | pytest.log |
| memory | generate/import | PASS | 0.77 | memory/generated-project.log |
| memory | plan | PASS | 0.33 | memory/plan.log |
| redis | generate/import | PASS | 0.67 | redis/generated-project.log |
| redis | plan | PASS | 0.33 | redis/plan.log |
| redis | plan-sentinel | PASS | 0.30 | redis/plan-sentinel.log |
| redis | plan-cluster | PASS | 0.30 | redis/plan-cluster.log |
| rabbitmq | generate/import | PASS | 0.67 | rabbitmq/generated-project.log |
| rabbitmq | plan | PASS | 0.31 | rabbitmq/plan.log |
| rabbitmq | plan-sentinel | PASS | 0.30 | rabbitmq/plan-sentinel.log |
| rabbitmq | plan-cluster | PASS | 0.33 | rabbitmq/plan-cluster.log |
| kafka | generate/import | PASS | 0.73 | kafka/generated-project.log |
| kafka | plan | PASS | 0.31 | kafka/plan.log |
| kafka | plan-sentinel | PASS | 0.31 | kafka/plan-sentinel.log |
| kafka | plan-cluster | PASS | 0.30 | kafka/plan-cluster.log |
