#  Distributed URL Shortener

![AWS Lambda](https://img.shields.io/badge/AWS_Lambda-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)
![Amazon DynamoDB](https://img.shields.io/badge/Amazon_DynamoDB-4053D6?style=for-the-badge&logo=amazondynamodb&logoColor=white)
![Python 3.12](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![AWS SAM](https://img.shields.io/badge/AWS_SAM-CC292B?style=for-the-badge&logo=aws&logoColor=white)

> A low-latency, interview-ready serverless URL shortener built on AWS Lambda, API Gateway, and DynamoDB. Architected with explicit trade-offs and clean OOP patterns to demonstrate production-grade system design principles.

---

## 💡 Highlights

* **Optimistic Concurrency:** Atomically prevents collisions with DynamoDB conditional writes rather than heavy application locks[cite: 2, 4].
* **Pluggable Hashing Algorithms:** Implements the Strategy Pattern to switch effortlessly between **Hash-Based** and **Counter-Based** key generation.
* **Clean & Testable Design:** Full separation of concerns with hand-rolled Base62 encoding and decoupled abstractions.

---

## 🏗️ Architecture Overview

```text
               ┌───────────────────────┐
               │    Client Request     │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │  API Gateway (REST)   │
               └───────────┬───────────┘
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│  CreateUrl    │   │   Redirect    │   │    Stats      │
│   Lambda      │   │    Lambda     │   │    Lambda     │
└──────┬────────┘   └──────┬────────┘   └──────┬────────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
              ┌─────────────────────────┐
              │  DynamoDB (urls/count)  │
              └─────────────────────────┘
