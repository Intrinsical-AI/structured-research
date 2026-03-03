"use client"

import { type ReactNode } from "react"
import { motion, AnimatePresence, type Variants } from "framer-motion"

/* ─── Shared easing ─── */
const ease = [0.22, 1, 0.36, 1] as const

/* ─── FadeIn ─── */
export function FadeIn({
  children,
  className,
  delay = 0,
  duration = 0.5,
  y = 12,
}: {
  children: ReactNode
  className?: string
  delay?: number
  duration?: number
  y?: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration, delay, ease }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ─── SlideIn (horizontal) ─── */
export function SlideIn({
  children,
  className,
  delay = 0,
  direction = "left",
}: {
  children: ReactNode
  className?: string
  delay?: number
  direction?: "left" | "right"
}) {
  const x = direction === "left" ? -20 : 20
  return (
    <motion.div
      initial={{ opacity: 0, x }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5, delay, ease }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ─── StaggerList — wraps children and staggers them ─── */
const staggerContainer: Variants = {
  hidden: {},
  show: {
    transition: {
      staggerChildren: 0.06,
    },
  },
}

const staggerItem: Variants = {
  hidden: { opacity: 0, y: 10 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.4, ease },
  },
}

export function StaggerList({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="show"
      className={className}
    >
      {children}
    </motion.div>
  )
}

export function StaggerItem({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <motion.div variants={staggerItem} className={className}>
      {children}
    </motion.div>
  )
}

/* ─── AnimatedTabContent — fade + slide on tab change ─── */
export function AnimatedTabContent({
  children,
  tabKey,
  className,
}: {
  children: ReactNode
  tabKey: string
  className?: string
}) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={tabKey}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.3, ease }}
        className={className}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}

/* ─── FloatingBlob — subtle floating animation for bg blurs ─── */
export function FloatingBlob({
  className,
  duration = 20,
  delay = 0,
}: {
  className?: string
  duration?: number
  delay?: number
}) {
  return (
    <motion.div
      className={className}
      animate={{
        y: [0, -18, 8, -12, 0],
        x: [0, 10, -6, 14, 0],
        scale: [1, 1.04, 0.97, 1.02, 1],
      }}
      transition={{
        duration,
        delay,
        repeat: Infinity,
        ease: "easeInOut",
      }}
    />
  )
}

/* ─── ScaleIn — for cards, badges, icons ─── */
export function ScaleIn({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode
  className?: string
  delay?: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, delay, ease }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

/* ─── Re-exports for convenience ─── */
export { motion, AnimatePresence }
