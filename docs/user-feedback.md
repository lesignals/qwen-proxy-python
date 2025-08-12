# User Feedback on Qwen Model Token Limits

## Observed Behavior

Through independent use of both the proxy and the qwen-code CLI tool, it has been found that after using approximately 130,000 to 150,000 tokens:

- The qwen-code CLI gets stuck and doesn't respond
- The proxy shows 504 Gateway Timeout streaming issues

This behavior indicates a practical limit on context length that users should be aware of when working with large contexts through either interface.