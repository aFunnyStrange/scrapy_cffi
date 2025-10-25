#ifndef BLOOM_H
#define BLOOM_H

#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef _WIN32
  #define BLOOM_API __declspec(dllexport)
#else
  #define BLOOM_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    size_t size;
    size_t bytes;
    size_t hash_count;
    size_t inserted;
    bool distributed;
    uint8_t *bit_array;
} BloomFilter;

BLOOM_API BloomFilter* bloom_init(size_t size, size_t expected_elements, size_t hash_count);
BLOOM_API void bloom_free(BloomFilter *filter);
BLOOM_API void bloom_add(BloomFilter *filter, const char *data, size_t len);
BLOOM_API bool bloom_exists(BloomFilter *filter, const char *data, size_t len);
BLOOM_API void bloom_clear(BloomFilter *filter);
BLOOM_API double bloom_estimated_false_positive_rate(BloomFilter *filter);
BLOOM_API size_t bloom_get_hash_count(BloomFilter *filter);
BLOOM_API size_t bloom_get_indices(BloomFilter *filter, const char *data, size_t len, size_t *out_indices);

#ifdef __cplusplus
}
#endif

#endif
