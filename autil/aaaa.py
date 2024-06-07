n = int(input())
A = list(map(int, input().split()))
dp = [0] * n
dp[0] = A[0]
for i in range(1, n):
    if i == 1:
        dp[i] = max(A[i], dp[i-1])
    else:
        dp[i] = max(A[i] + dp[i-2], dp[i-1])
print(dp[-1])