# Local model candidates

Research date: 2026-09-11. Proposal for the confirmed local vLLM deployment; no models downloaded, services started, or benchmarks run by this research task.

## Recommended first experiment

Use `Qwen/Qwen3-1.7B` in BF16 with thinking disabled. Its official card lists 1.7 billion parameters, Apache-2.0 licensing, agent/tool use, and vLLM support. This is a deliberately small starting point for the laptop's approximately 8 GB VRAM; actual retrieval-grounded answer quality must be evaluated. [Qwen model card](https://huggingface.co/Qwen/Qwen3-1.7B)

Tool parsing has first-party evidence: Qwen's vLLM guide demonstrates the Hermes parser for Qwen3, and the specific 1.7B tokenizer template serializes function names and arguments inside tool-call delimiters and handles tool responses. This supports trying `--enable-auto-tool-choice --tool-call-parser hermes`; it is not a measured correctness guarantee for this exact runtime/model combination. [Qwen deployment guide](https://qwen.readthedocs.io/en/latest/deployment/vllm.html#parsing-tool-calls), [1.7B tokenizer template](https://huggingface.co/Qwen/Qwen3-1.7B/blob/main/tokenizer_config.json)

Proposed initial Linux-container command, pending a pinned vLLM image and immutable model/tokenizer revisions:

```bash
vllm serve Qwen/Qwen3-1.7B \
  --served-model-name shop-chat \
  --dtype bfloat16 \
  --max-model-len 4096 \
  --max-num-seqs 2 \
  --gpu-memory-utilization 0.60 \
  --enforce-eager \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

These resource values are proposed starting limits. The latest local check found about 5.6 GiB free out of 8 GiB total, so begin with a 0.60 allocation fraction instead of reserving 0.80 of total memory. vLLM documents reducing context length and simultaneous sequences to reduce memory use; eager mode avoids CUDA-graph memory with a possible speed trade-off. Revisit eager mode after successful startup and measurement. [vLLM memory guidance](https://docs.vllm.ai/en/latest/configuration/conserving_memory/)

Set `chat_template_kwargs: {"enable_thinking": false}` on each request. Start with the model's suggested non-thinking sampling settings (`temperature=0.7`, `top_p=0.8`, `top_k=20`), then validate on the reviewed shop questions. The hard template switch avoids relying on a natural-language request to suppress thinking. [Qwen deployment guide](https://qwen.readthedocs.io/en/latest/deployment/vllm.html), [model recommendations](https://huggingface.co/Qwen/Qwen3-1.7B#best-practices)

Application budgets are design proposals: at most 512 generated tokens per model call, at most 3 model calls and 2 tool rounds per shopper question, all inside the accepted request's two-minute deadline. Count the rendered prompt, tool schemas, retrieved evidence, conversation context, and output reserve against 4096 tokens on every call. Keep full durable history separately; select a bounded context without cutting a tool interaction in half. Reject or ask the shopper to shorten an oversized message before acceptance. The one or two inference slots are distinct from 100 open browser conversations. The 5 questions/second and ten-second p95 target remains unvalidated.

At the approximate parameter count, BF16 weights alone are around 3.4 GB decimal (1.7 billion times two bytes). This arithmetic excludes runtime buffers, KV cache, allocator overhead, and desktop GPU use; it does not establish that startup or sustained traffic fits.

## Fallback

If memory is insufficient, first try one sequence and a smaller context with explicit product limits. The official `Qwen/Qwen3-1.7B-FP8` is a candidate for reducing weight memory; its card describes blockwise FP8 quantization. Verify the selected vLLM/CUDA image's kernel support on this laptop and re-run quality tests before adopting it. No quantized checkpoint is assumed interchangeable with BF16 for cache correctness. [Official FP8 checkpoint](https://huggingface.co/Qwen/Qwen3-1.7B-FP8), [Qwen quantized serving](https://qwen.readthedocs.io/en/latest/deployment/vllm.html#serving-quantized-models)

A quantized 4B model can be evaluated later if the 1.7B model fails tool/answer-quality requirements, but it adds another checkpoint and kernel choice. Do not promise that a larger model meets the same local capacity target without measurement.

## CPU embeddings

Use `BAAI/bge-small-en-v1.5`: English, 384-dimensional vectors, 512-token sequence limit, MIT license. Its card supports Sentence Transformers and recommends a retrieval instruction for queries, with no instruction on indexed passages. [BAAI model card](https://huggingface.co/BAAI/bge-small-en-v1.5)

Load through `SentenceTransformer(..., device="cpu", revision="<verified-commit-sha>")`; the documented API supports explicit CPU placement and commit revisions. Keep `trust_remote_code=False`. Pin the commit during implementation after selecting and verifying it; this note deliberately supplies no guessed revision. [Sentence Transformers API](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)

For product retrieval, prepend `Represent this sentence for searching relevant passages: ` to the query and embed product text without that prefix. For semantic-cache question similarity, use unprefixed questions on both sides. Keep the two collections' preprocessing identities distinct, even when they share a model. Normalize consistently and calibrate cache thresholds against near misses in category, numerical filters, and intent; similarity alone is insufficient for answer reuse. The prefix behavior comes from the model card; the cache preprocessing and validation rules are this project's proposed design. [BAAI usage guidance](https://huggingface.co/BAAI/bge-small-en-v1.5#frequently-asked-questions)

Run bounded CPU embedding batches for ingestion and reserve capacity for interactive queries. Version catalog vectors with the embedding revision and preprocessing configuration. Cache compatibility also includes the chat-model revision and prompt/tool-schema versions. Do not run bulk description generation concurrently with interactive GPU benchmarking.

## Required verification before adopting

1. Pin vLLM container digest, chat weights/tokenizer revision, embedding revision, and application dependencies together.
2. Verify GPU visibility inside the selected container, cold startup, and available memory; Docker/WSL running alone does not prove GPU-container compatibility.
3. Test actual automatic calls, multi-turn tool results, invalid arguments, missing products, clarification, and grounded final responses. Validate every tool argument server-side regardless of parser support. [vLLM tool-calling behavior](https://docs.vllm.ai/en/latest/features/tool_calling/)
4. Measure warm/cold latency, actual inference concurrency, quality, and end-to-end load on this machine. Report achieved capacity separately from the agreed production design targets.
