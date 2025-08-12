# Project Goal and Architecture

## Goal

The primary goal of this project is to create an OpenAI-compatible API proxy server that allows any application designed to work with OpenAI's APIs to seamlessly use Qwen models from qwen oauth sub of qwen-code cli  . This includes full support for streaming and so on . 

the source code of qwen-code cli is in ./qwen-code . its been added to .gitignore but llm should find and search it learn more . 

The core problem this solves is the "cold start" issue for new models. By exposing Qwen's capabilities through a widely-adopted API standard (OpenAI's), we can leverage the vast ecosystem of existing tools and applications, making Qwen's models immediately useful to a broad audience.

in simple terms it is a drop and replacement for qwen-code for broad use case 
qwen api -- > qwen code cli --- > works only in termianl for  coding 
            (checks auth and refresh )
qwen api -- > proxxy ---> open ai OpenAI-compatible api --> any tools that uses openai api
            (checks auth and refresh)

## Architecture

The proxy server sits between an OpenAI-compatible client and the Qwen API, translating requests and responses in real-time.

```
[OpenAI Client] <--> [Proxy Server] <--> [Qwen API]
      |                   |                  |
OpenAI Format      Translation Layer      Qwen Models
```

### Key Components:

1.  **API Translation Layer**: This is the heart of the proxy. It converts incoming OpenAI-formatted requests into the format expected by the Qwen API, and then translates the Qwen API's response back into the OpenAI format.

2.  **Authentication Management**: The proxy is designed to be user-friendly by automatically using the same authentication credentials as the official Qwen CLI tool. It reads the `oauth_creds.json` file, uses the access token, and handles token refreshes automatically. This means that if a user is already logged into the Qwen CLI, the proxy works out-of-the-box without requiring a separate login. Users can authenticate using either the official `qwen-code` CLI tool or the proxy's built-in authentication script with QR code support. For a detailed explanation of the authentication process, see `authentication.md` and `qr-authentication.md`.

3.  **Server Implementation**: The proxy is built as a Node.js server using the Express.js framework. It exposes the necessary OpenAI-compatible endpoints, such as `/v1/chat/completions` and `/v1/embeddings`.

## Architecture

### Key Components:

1.  **API Translation Layer**: This is the heart of the proxy. It converts incoming OpenAI-formatted requests into the format expected by the Qwen API, and then translates the Qwen API's response back into the OpenAI format.

2.  **Authentication Management**: The proxy is designed to be user-friendly by automatically using the same authentication credentials as the official Qwen CLI tool. It reads the `oauth_creds.json` file, uses the access token, and handles token refreshes automatically. This means that if a user is already logged into the Qwen CLI, the proxy works out-of-the-box without requiring a separate login. Users can authenticate using either the official `qwen-code` CLI tool or the proxy's built-in authentication script with QR code support. For a detailed explanation of the authentication process, see `authentication.md` and `qr-authentication.md`.

3.  **Server Implementation**: The proxy is built as a Node.js server using the Express.js framework. It exposes the necessary OpenAI-compatible endpoints, such as `/v1/chat/completions` and `/v1/embeddings`.

## Supported Endpoints

Based on the implementation in `src/index.js`, the proxy supports the following endpoints:
- `POST /v1/chat/completions` - Chat completions with streaming support
- `GET /v1/models` - List available models (returns mock data)
- `POST /v1/embeddings` - Text embeddings generation
- `GET /health` - Health check endpoint
- `POST /auth/initiate` - Authentication initiation endpoint
- `POST /auth/poll` - Authentication polling endpoint

## Key Features

### Authentication
- Automatic token refresh 30 seconds before expiration
- Concurrent request handling with refresh queuing
- Fallback retry logic for authentication errors
- Support for custom endpoints from credentials

### Token Management
- Terminal display of input token estimates
- API-returned token usage statistics (prompt, completion, total)
- Automatic context window management
- Proactive token limit handling

### Error Handling
- Automatic retry for authentication errors
- Graceful handling of 504 Gateway Timeout issues
- Detailed error logging with debug file output
- Specific handling for context length exceeded errors

### Logging and Debugging
- Configurable debug logging with file output
- Log file rotation with configurable limits
- Color-coded terminal output for different message types
- Detailed API request/response logging in debug files

## Configuration

The proxy server can be configured using environment variables. Create a `.env` file in the project root or set the variables directly in your environment.

- `LOG_FILE_LIMIT`: Maximum number of debug log files to keep (default: 20)
- `DEBUG_LOG`: Set to `true` to enable debug logging (default: false)
- `HOST`: Server host (default: localhost)
- `PORT`: Server port (default: 8080)

## Token Limits and Performance

Users might face errors or 504 Gateway Timeout issues when using contexts with 130,000 to 150,000 tokens or more. This appears to be a practical limit for Qwen models. For detailed information based on user feedback, see `user-feedback.md`.

The proxy now displays token counts in the terminal for each request, showing both input token estimates and API-returned usage statistics (prompt, completion, and total tokens).
