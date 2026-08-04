"use client";

import { motion, useReducedMotion, type Variants } from "framer-motion";
import { useHydrated } from "@/lib/use-hydrated";

const variants: Variants = {
  hidden: { opacity: 0, y: 16, scale: 0.995 },
  visible: { opacity: 1, y: 0, scale: 1 },
};

/** Scroll reveal disabled entirely under prefers-reduced-motion. */
export function Reveal({
  children,
  className,
  index = 0,
  delay,
}: {
  children: React.ReactNode;
  className?: string;
  index?: number;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  const hydrated = useHydrated();
  if (hydrated && reduced) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={className}
      variants={variants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.12 }}
      transition={{
        duration: 0.48,
        ease: [0.22, 1, 0.36, 1],
        delay: delay ?? (index % 4) * 0.06,
      }}
    >
      {children}
    </motion.div>
  );
}
