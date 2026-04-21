export function scrollMessageListToBottom(scrollRoot: HTMLDivElement | null) {
  const viewport = getScrollViewport(scrollRoot)
  if (!viewport) {
    return
  }

  viewport.scrollTo({
    top: viewport.scrollHeight,
    behavior: 'smooth',
  })
}

function getScrollViewport(scrollRoot: HTMLDivElement | null) {
  if (!scrollRoot) {
    return null
  }

  const viewport = scrollRoot.querySelector('[data-radix-scroll-area-viewport]')
  return viewport instanceof HTMLDivElement ? viewport : scrollRoot
}
