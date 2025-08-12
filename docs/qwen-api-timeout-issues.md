# Qwen API Timeout and Streaming Issues

## Overview

This document analyzes potential timeout and streaming issues that may occur when using the Qwen API through the OpenAI-compatible proxy. The information is based on analysis of both the proxy implementation and the qwen-code CLI tool source code.

## Known Issues

### 504 Gateway Timeout Errors

The error message you've encountered:
```
API Error (500 {"error":{"message":"Error from provider: {\"error\":{\"message\":\"Qwen API error: 504 \\\"stream timeout\\\"\",\"type\":\"internal_server_error\"}}Error: Error from provider: {\"error\":{\"message\":\"Qwen API error: 504 \\\"stream timeout\\\"\",\"type\":\"internal_server_error\"}}
```

This indicates that the Qwen API is experiencing timeout issues on their backend, particularly during streaming operations.

## Root Cause Analysis

Based on the source code analysis:

1. **Timeout Configuration**: The proxy sets a 5-minute timeout for API requests (300,000 ms) in both chat completions and embeddings endpoints.

2. **Streaming Complexity**: Streaming responses require maintaining long-lived connections, which are more susceptible to network interruptions and server-side timeouts.

3. **Qwen API Backend**: The 504 "stream timeout" error originates from Qwen's infrastructure, suggesting that their streaming endpoint has internal timeout limits.

4. **Token Expiration Issues**: Expired access tokens were causing authentication failures that manifested as 504 Gateway Timeout errors from Qwen's API. The proxy was not validating token expiration before use.

## Solution Implementation

### Token Validation and Refresh

The proxy has been enhanced with robust token management that matches the official qwen-code CLI implementation:

1. **Automatic Token Validation**: Before each API request, the proxy now checks if the access token is still valid using the same logic as qwen-code.

2. **Proactive Token Refresh**: Tokens are automatically refreshed 30 seconds before they expire, preventing authentication failures.

3. **Error-Based Retry Logic**: When 504 Gateway Timeout errors occur (which were often caused by expired tokens), the proxy now:
   - Detects the authentication error
   - Automatically refreshes the access token
   - Retries the request with the new token
   - Only fails if the retry also fails

4. **Concurrent Request Handling**: Multiple simultaneous requests are handled efficiently using a `refreshPromise` pattern that prevents multiple simultaneous token refresh attempts.

### Logging and Monitoring

The enhanced implementation provides detailed logging to help diagnose token-related issues:

- **Token Status**: Shows when tokens are valid vs. when they need refreshing
- **Refresh Operations**: Logs when token refresh starts and completes
- **Retry Attempts**: Shows when auth errors trigger automatic retries
- **Success/Failure**: Clear indication of whether retries succeed or fail

### Benefits

1. **Eliminates 504 Errors**: Most 504 Gateway Timeout errors caused by expired tokens are now resolved automatically.

2. **Improved Reliability**: No more need to manually restart the proxy when tokens expire.

3. **Better User Experience**: Requests succeed automatically without user intervention.

4. **Alignment with Official Tool**: Implementation now matches the robust token handling of the official qwen-code CLI.

## Recommendations

### For Proxy Users

1. **Reduce Input Size**: Large prompts are more likely to trigger timeouts. Try breaking large requests into smaller chunks.

2. **Check Network Connectivity**: Ensure stable internet connection, especially for streaming requests.

3. **Retry Logic**: Implement client-side retry logic for transient timeout errors.

### For Proxy Configuration

1. **Adjust Timeout Settings**: Consider increasing the timeout value in the axios requests if your use case requires longer processing times.

2. **Better Error Handling**: Implement more specific handling for 504 errors to provide better user feedback.

3. **Streaming Fallback**: Consider implementing fallback logic that switches from streaming to non-streaming mode when timeouts occur.

## Implementation Notes

The current proxy implementation in `src/qwen/api.js` has basic error handling that captures HTTP status codes and error responses. However, it could be enhanced to:

1. Specifically detect and handle 504 Gateway Timeout errors
2. Provide more informative error messages to users
3. Implement retry logic for transient timeout issues
4. Add configuration options for timeout values

## Conclusion

The 504 "stream timeout" errors are server-side issues from Qwen's API infrastructure. While the proxy cannot prevent these errors, it can be enhanced to handle them more gracefully and provide better guidance to users on how to work around them.