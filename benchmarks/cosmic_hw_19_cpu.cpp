#include <openssl/crypto.h>
#include <openssl/sha.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

constexpr std::size_t kSites = 64;
constexpr std::size_t kReceipts = 128;
constexpr std::size_t kReceiptsPerDigest = 10;
constexpr std::size_t kDigests = 13;
constexpr std::uint16_t kFullDomain = 0x434f;
constexpr std::uint16_t kPartialDomainBase = 0x4340;
constexpr const char* kExpectedLastDigest =
    "c31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2";

volatile std::uint64_t digest_sink = 0;
volatile std::int8_t stimulus_source = 100;

std::uint64_t pack_receipt(std::uint16_t tick, std::uint8_t site,
                           std::uint8_t before, std::uint8_t after,
                           std::int8_t stimulus, std::uint8_t ordinal) {
  return (static_cast<std::uint64_t>(tick) << 24) |
         (static_cast<std::uint64_t>(site) << 18) |
         (static_cast<std::uint64_t>(before) << 16) |
         (static_cast<std::uint64_t>(after) << 14) |
         (static_cast<std::uint64_t>(static_cast<std::uint8_t>(stimulus)) << 6) |
         ordinal;
}

std::string hex_digest(const std::array<unsigned char, SHA256_DIGEST_LENGTH>& digest) {
  std::ostringstream out;
  out << std::hex << std::setfill('0');
  for (unsigned char byte : digest) out << std::setw(2) << static_cast<unsigned>(byte);
  return out.str();
}

std::array<unsigned char, SHA256_DIGEST_LENGTH> proof_edge_operation() {
  const std::int8_t runtime_stimulus = stimulus_source;
  std::array<std::uint8_t, kSites> phase{};
  std::array<std::int8_t, kSites> previous_stimulus{};
  std::array<bool, kSites> dirty{};
  std::array<std::uint64_t, kReceipts> receipts{};
  std::size_t receipt_count = 0;

  for (std::uint16_t tick = 1; tick <= 2; ++tick) {
    std::array<std::uint8_t, kSites> next = phase;
    std::array<bool, kSites> changed{};
    std::array<bool, kSites> dirty_next{};

    for (std::size_t site = 0; site < kSites; ++site) {
      const std::int8_t stimulus = runtime_stimulus;
      if (!dirty[site] && stimulus == previous_stimulus[site]) continue;

      const int row = static_cast<int>(site / 8);
      const int col = static_cast<int>(site % 8);
      int neighbors = 0;
      int neighbor_sum2 = 0;
      auto add_neighbor = [&](std::size_t other) {
        ++neighbors;
        neighbor_sum2 += phase[other];
      };
      if (row > 0) add_neighbor(site - 8);
      if (row < 7) add_neighbor(site + 8);
      if (col > 0) add_neighbor(site - 1);
      if (col < 7) add_neighbor(site + 1);

      const int coupling100 = ((row + col) % 2 == 0) ? 75 : 50;
      const int threshold100 = phase[site] == 1 ? 5 : (((row + col) % 2 == 0) ? 50 : 35);
      const int drive_num = 2 * neighbors * stimulus +
                            coupling100 * (neighbor_sum2 - neighbors * phase[site]);
      const int limit = 2 * neighbors * threshold100;
      if (drive_num >= limit && phase[site] < 2) next[site] = phase[site] + 1;
      if (drive_num <= -limit && phase[site] > 0) next[site] = phase[site] - 1;
      changed[site] = next[site] != phase[site];
    }

    std::uint8_t ordinal = 0;
    for (std::size_t site = 0; site < kSites; ++site) {
      if (!changed[site]) continue;
      receipts[receipt_count++] = pack_receipt(
          tick, static_cast<std::uint8_t>(site), phase[site], next[site],
          runtime_stimulus, ordinal++);
      dirty_next[site] = true;
      const int row = static_cast<int>(site / 8);
      const int col = static_cast<int>(site % 8);
      if (row > 0) dirty_next[site - 8] = true;
      if (row < 7) dirty_next[site + 8] = true;
      if (col > 0) dirty_next[site - 1] = true;
      if (col < 7) dirty_next[site + 1] = true;
    }
    phase = next;
    dirty = dirty_next;
    previous_stimulus.fill(runtime_stimulus);
  }

  if (receipt_count != kReceipts || !std::all_of(phase.begin(), phase.end(), [](auto p) { return p == 2; })) {
    throw std::runtime_error("transition/receipt oracle mismatch");
  }

  std::array<unsigned char, SHA256_DIGEST_LENGTH> last_digest{};
  for (std::size_t sequence = 0; sequence < kDigests; ++sequence) {
    const std::size_t start = sequence * kReceiptsPerDigest;
    const std::size_t count = std::min(kReceiptsPerDigest, kReceipts - start);
    const std::uint16_t domain = count == kReceiptsPerDigest
        ? kFullDomain
        : static_cast<std::uint16_t>(kPartialDomainBase | count);
    std::array<unsigned char, 54> message{};
    message[0] = static_cast<unsigned char>(domain >> 8);
    message[1] = static_cast<unsigned char>(domain);
    message[2] = static_cast<unsigned char>(sequence >> 8);
    message[3] = static_cast<unsigned char>(sequence);
    for (std::size_t slot = 0; slot < count; ++slot) {
      const std::uint64_t receipt = receipts[start + slot];
      for (std::size_t byte = 0; byte < 5; ++byte) {
        message[4 + slot * 5 + byte] =
            static_cast<unsigned char>(receipt >> (8 * (4 - byte)));
      }
    }
    SHA256(message.data(), message.size(), last_digest.data());
  }
  digest_sink ^= static_cast<std::uint64_t>(last_digest[0]) << 56 |
                 static_cast<std::uint64_t>(last_digest[31]);
  return last_digest;
}

double percentile(std::vector<double> values, double fraction) {
  std::sort(values.begin(), values.end());
  const std::size_t index = std::min(values.size() - 1,
      static_cast<std::size_t>(std::ceil(fraction * values.size())) - 1);
  return values[index];
}

}  // namespace

int main(int argc, char** argv) {
  const std::uint64_t iterations = argc > 1 ? std::stoull(argv[1]) : 20000;
  const std::size_t samples = argc > 2 ? std::stoull(argv[2]) : 31;
  const std::uint64_t warmup = argc > 3 ? std::stoull(argv[3]) : 2000;
  const std::size_t latency_samples = argc > 4 ? std::stoull(argv[4]) : 10000;
  if (iterations == 0 || samples < 3 || warmup == 0 || latency_samples < 100) return 2;

  const auto oracle = proof_edge_operation();
  const std::string observed_digest = hex_digest(oracle);
  if (observed_digest != kExpectedLastDigest) {
    std::cerr << "CPU oracle mismatch: " << observed_digest << "\n";
    return 3;
  }
  for (std::uint64_t i = 0; i < warmup; ++i) proof_edge_operation();

  std::vector<double> ns_per_operation;
  ns_per_operation.reserve(samples);
  for (std::size_t sample = 0; sample < samples; ++sample) {
    const auto start = std::chrono::steady_clock::now();
    for (std::uint64_t i = 0; i < iterations; ++i) proof_edge_operation();
    const auto stop = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration<double, std::nano>(stop - start).count();
    ns_per_operation.push_back(elapsed / static_cast<double>(iterations));
  }

  const double mean = std::accumulate(ns_per_operation.begin(), ns_per_operation.end(), 0.0) /
                      static_cast<double>(ns_per_operation.size());
  std::vector<double> single_operation_ns;
  single_operation_ns.reserve(latency_samples);
  for (std::size_t sample = 0; sample < latency_samples; ++sample) {
    const auto start = std::chrono::steady_clock::now();
    proof_edge_operation();
    const auto stop = std::chrono::steady_clock::now();
    single_operation_ns.push_back(
        std::chrono::duration<double, std::nano>(stop - start).count());
  }
  std::cout << std::fixed << std::setprecision(3)
            << "{\n"
            << "  \"oracle_match\": true,\n"
            << "  \"last_digest\": \"" << observed_digest << "\",\n"
            << "  \"iterations_per_sample\": " << iterations << ",\n"
            << "  \"samples\": " << samples << ",\n"
            << "  \"warmup_iterations\": " << warmup << ",\n"
            << "  \"single_operation_latency_samples\": " << latency_samples << ",\n"
            << "  \"mean_ns_per_operation\": " << mean << ",\n"
            << "  \"median_ns_per_operation\": " << percentile(ns_per_operation, 0.50) << ",\n"
            << "  \"sample_mean_p99_ns_per_operation\": " << percentile(ns_per_operation, 0.99) << ",\n"
            << "  \"p99_single_operation_ns\": " << percentile(single_operation_ns, 0.99) << ",\n"
            << "  \"mean_operations_per_second\": " << (1.0e9 / mean) << ",\n"
            << "  \"runtime_input_source\": \"volatile int8_t\",\n"
            << "  \"openssl_version\": \"" << OpenSSL_version(OPENSSL_VERSION) << "\",\n"
            << "  \"digest_sink\": " << digest_sink << "\n"
            << "}\n";
  return 0;
}
