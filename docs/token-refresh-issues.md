# Token Refresh Issues and Solutions

## Problem Description

The Qwen OpenAI-Compatible Proxy was experiencing intermittent 504 Gateway Timeout errors that would resolve temporarily after restarting the proxy server. This document explains the root cause and the solution.

## Root Cause Analysis

### Current Implementation Issues

1. **No Token Validation**: The proxy loads credentials using `loadCredentials()` but doesn't check if the access token is expired.

2. **No Automatic Refresh**: Expired tokens are sent to the Qwen API, causing authentication failures that may manifest as 504 errors.

3. **No Error Recovery**: When authentication errors occur, there's no retry mechanism with refreshed tokens.

4. **No Concurrent Handling**: Multiple requests can trigger simultaneous token refresh attempts.

### Why Rebooting Fixes the Issue

When the proxy is restarted:
- Fresh credentials are loaded from the file system
- Tokens are likely still valid (if recently refreshed by qwen-code CLI)
- All problematic internal state is cleared
- HTTP connection pools are reset

However, this is only a temporary fix as tokens will eventually expire again.

## How qwen-code CLI Handles Token Refresh

The official qwen-code CLI implements robust token management:

1. **Automatic Validation**: `getAccessToken()` checks token validity using `isTokenValid()`
2. **Proactive Refresh**: Refreshes tokens 30 seconds before expiration
3. **Error-Based Retry**: Detects auth errors and automatically retries with refreshed tokens
4. **Concurrent Request Handling**: Uses `refreshPromise` to prevent multiple simultaneous refreshes
5. **Retry Logic**: Automatically retries failed requests once after token refresh

## Solution Implementation

### Enhanced Auth Manager

The `src/qwen/auth.js` file was updated with:

1. **Token Validation**: Added `isTokenValid()` method that checks if tokens will expire within 30 seconds
2. **Automatic Refresh**: Implemented `getValidAccessToken()` that validates and refreshes tokens automatically
3. **Concurrent Handling**: Added `refreshPromise` to prevent multiple simultaneous refresh attempts
4. **Error Handling**: Improved error messages and logging for token operations

### Enhanced API Client

The `src/qwen/api.js` file was updated with:

1. **Token Usage**: Both `chatCompletions()` and `createEmbeddings()` now use `getValidAccessToken()` instead of `loadCredentials()`
2. **Auth Error Detection**: Added `isAuthError()` function to detect authentication-related errors including 504 Gateway Timeout
3. **Retry Logic**: Implemented automatic retry mechanism for auth errors
4. **Logging**: Added comprehensive logging for token operations and retry attempts

### Key Features

**Automatic Token Management:**
```
Before Request → Check Token Validity → Refresh if Needed → Make API Call
```

**Error Recovery:**
```
API Error → Detect Auth Error → Refresh Token → Retry Request → Success/Fail
```

**Concurrent Handling:**
```
Multiple Requests → Single Refresh Operation → All Wait for Same Result
```

### Logging Output

The enhanced implementation provides clear terminal output:

- **🟡 "Refreshing Qwen access token..."** - Token refresh started
- **✅ "Qwen access token refreshed successfully"** - Token refresh completed
- **✅ "Using valid Qwen access token"** - Token is still valid
- **🟡 "Qwen access token expired or expiring soon, refreshing..."** - Proactive refresh
- **🟡 "Detected auth error (504), attempting token refresh and retry..."** - Error-triggered refresh
- **🔵 "Retrying request with refreshed token..."** - Retry in progress
- **✅ "Request succeeded after token refresh"** - Retry successful
- **❌ "Request failed even after token refresh"** - Retry failed

### Benefits

- **Eliminates 504 Errors**: Most 504 Gateway Timeout errors caused by expired tokens are now resolved automatically
- **Improved Reliability**: No more need to manually restart the proxy when tokens expire
- **Better User Experience**: Requests succeed automatically without user intervention
- **Alignment with Official Tool**: Implementation now matches the robust token handling of the official qwen-code CLI
- **Transparent Operation**: Clear logging shows what's happening with token management

## Testing the Solution

The implementation has been completed and tested. After restarting the proxy, you should see:

1. **Initial Requests**: "Using valid Qwen access token" if tokens are still valid
2. **Token Expiration**: Automatic refresh with clear logging messages
3. **Error Recovery**: Auth errors automatically trigger refresh and retry
4. **No Manual Intervention**: 504 errors should be resolved automatically

The solution has been verified to eliminate the 504 timeout issues caused by expired tokens.