#include "bloom.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

// FNV-1a hash
static uint32_t fnv1a_hash_bytes(const uint8_t *data, size_t len, size_t seed) {
    uint32_t hash = 2166136261u ^ (uint32_t)seed;
    for (size_t i = 0; i < len; i++) {
        hash ^= data[i];
        hash *= 16777619u;
    }
    return hash;
}

static void set_bit(uint8_t *array, size_t index) {
    array[index / 8] |= (1 << (index % 8));
}

static bool get_bit(uint8_t *array, size_t index) {
    return (array[index / 8] >> (index % 8)) & 1;
}

// calc k
static size_t optimal_k(size_t m, size_t n) {
    return (size_t)round((double)m / n * log(2.0));
}

BloomFilter* bloom_init(size_t size, size_t expected_elements, size_t hash_count) {
    BloomFilter *filter = (BloomFilter*)malloc(sizeof(BloomFilter));
    if (!filter) return NULL;
    filter->size = size;
    filter->bytes = (size + 7) / 8;
    filter->bit_array = (uint8_t*)calloc(filter->bytes, 1);
    filter->inserted = 0;
    filter->distributed = false;
    filter->hash_count = hash_count ? hash_count : optimal_k(size, expected_elements);
    if (filter->hash_count < 1) filter->hash_count = 1;
    return filter;
}

void bloom_free(BloomFilter *filter) {
    if (!filter) return;
    free(filter->bit_array);
    free(filter);
}

void bloom_add(BloomFilter *filter, const char *data, size_t len) {
    const uint8_t *buf = (const uint8_t*)data;
    for (size_t i = 0; i < filter->hash_count; i++) {
        size_t index = fnv1a_hash_bytes(buf, len, i) % filter->size;
        set_bit(filter->bit_array, index);
    }
    filter->inserted++;
}

bool bloom_exists(BloomFilter *filter, const char *data, size_t len) {
    const uint8_t *buf = (const uint8_t*)data;
    for (size_t i = 0; i < filter->hash_count; i++) {
        size_t index = fnv1a_hash_bytes(buf, len, i) % filter->size;
        if (!get_bit(filter->bit_array, index)) return false;
    }
    return true;
}

void bloom_clear(BloomFilter *filter) {
    memset(filter->bit_array, 0, filter->bytes);
    filter->inserted = 0;
}

double bloom_estimated_false_positive_rate(BloomFilter *filter) {
    if (filter->inserted == 0) return 0.0;
    double m = (double)filter->size;
    double k = (double)filter->hash_count;
    double n = (double)filter->inserted;
    return pow(1.0 - exp(-k * n / m), k);
}

size_t bloom_get_hash_count(BloomFilter *filter) {
    return filter ? filter->hash_count : 0;
}

size_t bloom_get_indices(BloomFilter *filter, const char *data, size_t len, size_t *out_indices) {
    const uint8_t *buf = (const uint8_t*)data;
    for (size_t i = 0; i < filter->hash_count; i++) {
        out_indices[i] = fnv1a_hash_bytes(buf, len, i) % filter->size;
    }
    return filter->hash_count;
}
