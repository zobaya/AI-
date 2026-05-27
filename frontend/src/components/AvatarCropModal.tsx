import { useState, useCallback } from 'react'
import Cropper from 'react-easy-crop'
import type { Area, Point } from 'react-easy-crop'

interface AvatarCropModalProps {
  imageSrc: string
  onConfirm: (blob: Blob) => void
  onCancel: () => void
}

export default function AvatarCropModal({ imageSrc, onConfirm, onCancel }: AvatarCropModalProps) {
  const [crop, setCrop] = useState<Point>({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(1)
  const [croppedAreaPixels, setCroppedAreaPixels] = useState<Area | null>(null)

  const onCropComplete = useCallback((_croppedArea: Area, croppedPixels: Area) => {
    setCroppedAreaPixels(croppedPixels)
  }, [])

  const handleConfirm = async () => {
    if (!croppedAreaPixels) return
    const blob = await getCroppedImg(imageSrc, croppedAreaPixels)
    onConfirm(blob)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.5)' }}
    >
      <div
        className="rounded-xl shadow-xl flex flex-col"
        style={{ background: 'var(--surface)', width: 400, maxWidth: '90vw' }}
      >
        {/* 标题 */}
        <div className="px-5 py-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
          <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>裁切头像</span>
        </div>

        {/* 裁切区域 */}
        <div className="relative" style={{ width: '100%', height: 300, background: '#1a1a1a' }}>
          <Cropper
            image={imageSrc}
            crop={crop}
            zoom={zoom}
            aspect={1}
            cropShape="round"
            showGrid={false}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={onCropComplete}
          />
        </div>

        {/* 缩放滑块 */}
        <div className="px-5 py-3 flex items-center gap-3">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>缩放</span>
          <input
            type="range"
            min={1}
            max={3}
            step={0.1}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            className="flex-1"
          />
        </div>

        {/* 按钮 */}
        <div className="px-5 py-3 border-t flex justify-end gap-2" style={{ borderColor: 'var(--border)' }}>
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm cursor-pointer border"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            取消
          </button>
          <button
            onClick={handleConfirm}
            className="px-4 py-2 rounded-lg text-sm cursor-pointer text-white"
            style={{ background: 'var(--primary)' }}
          >
            确认上传
          </button>
        </div>
      </div>
    </div>
  )
}

/** 将裁切区域输出为 Blob */
async function getCroppedImg(imageSrc: string, pixelCrop: Area): Promise<Blob> {
  const image = await createImage(imageSrc)
  const canvas = document.createElement('canvas')
  canvas.width = pixelCrop.width
  canvas.height = pixelCrop.height
  const ctx = canvas.getContext('2d')!

  ctx.drawImage(
    image,
    pixelCrop.x,
    pixelCrop.y,
    pixelCrop.width,
    pixelCrop.height,
    0,
    0,
    pixelCrop.width,
    pixelCrop.height,
  )

  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob!), 'image/jpeg', 0.9)
  })
}

function createImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.addEventListener('load', () => resolve(img))
    img.addEventListener('error', reject)
    img.crossOrigin = 'anonymous'
    img.src = url
  })
}
