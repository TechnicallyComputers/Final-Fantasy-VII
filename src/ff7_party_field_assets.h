#ifndef FF7_PARTY_FIELD_ASSETS_H
#define FF7_PARTY_FIELD_ASSETS_H
#include <stddef.h>
#include <stdint.h>

typedef struct FF7FieldAssetSource {
    const uint8_t* bsx;
    size_t size;
    unsigned model;
} FF7FieldAssetSource;

/* Pure bounded builders for owned-disc data. Output must not overlap inputs.
 * Returns output bytes, zero on failure; callers publish only complete builds.
 * BSX reserve includes the original loader's descriptor/packet scratch region.
 * Script builder appends new visible entities; existing entity numbers and
 * relative script branches stay unchanged. Runtime insertion requires the
 * independent CHAR counter adapter in ff7_party_field_state.c. */
size_t ff7_field_append_script(const uint8_t* input,size_t bytes,
                              const uint8_t* guests,unsigned count,
                              uint8_t* output,size_t capacity);
size_t ff7_field_append_models(const uint8_t* input,size_t bytes,
                              const FF7FieldAssetSource* sources,unsigned count,
                              uint8_t* output,size_t capacity,size_t* reserve);
int ff7_field_asset_metadata(const FF7FieldAssetSource* source,uint8_t output[8]);
size_t ff7_field_decode_lzs(const uint8_t* input,size_t bytes,uint8_t* output,size_t capacity);
#endif
