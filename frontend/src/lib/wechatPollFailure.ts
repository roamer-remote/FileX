/** 微信 OAuth 状态轮询连续失败阈值，超过后提示用户刷新二维码。 */
export const WECHAT_POLL_FAIL_THRESHOLD = 5

export function shouldAbortWechatPoll(failStreak: number): boolean {
  return failStreak >= WECHAT_POLL_FAIL_THRESHOLD
}
