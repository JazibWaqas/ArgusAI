from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
import timm


class SpectralFusionModel(nn.Module):
    def __init__(self, num_classes: int = 2) -> None:
        super().__init__()
        
        # 1. Semantic Branch (ConvNeXt Small)
        self.semantic_branch = timm.create_model('convnext_small.fb_in22k_ft_in1k', pretrained=False, num_classes=0)
        
        # 2. Spectral Branch (FFT Head)
        self.spectral_branch = nn.Sequential(
            nn.AdaptiveAvgPool2d((64, 64)), nn.Flatten(),
            nn.Linear(64*64, 256), nn.ReLU()
        )
        
        # 3. SPAI Branch (Masked Frequency Head)
        self.spai_branch = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((32, 32)),
            nn.Flatten(1),
            nn.Linear(32*32*32, 256) # 32768
        )
        
        # 4. SRM Branch (Spatial Rich Model Head)
        self.srm_conv = nn.Conv2d(1, 3, kernel_size=5, padding=2, bias=False)
        self.srm_branch = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((16, 16)),
            nn.Flatten(1),
            nn.Linear(32*16*16, 256) # 8192
        )
        
        # 5. Chroma Branch (YCbCr Head)
        self.chroma_branch = nn.Sequential(
            nn.Conv2d(2, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((32, 32)),
            nn.Flatten(1),
            nn.Linear(16*32*32, 128) # 16384
        )
        
        # 6. Robustness Branch (Feature Drift Head)
        self.robustness_branch = nn.Sequential(
            nn.Linear(768, 256),
            nn.ReLU(),
            nn.Linear(256, 128)
        )

        # Final Fusion Head (Standardized 0=Real, 1=AI)
        # Total dims: 768 + 256 + 256 + 256 + 128 + 128 = 1792
        self.fusion_head = nn.Sequential(
            nn.Linear(1792, 1024),
            nn.ReLU(inplace=True),
            nn.Dropout(p=0.3),
            nn.Linear(1024, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass with integrated signal extraction matching training_model.py.
        - x should be a normalized image tensor [B, 3, 224, 224]
        """
        # 1. Semantic Features
        sem_feat = self.semantic_branch(x)

        # Grayscale for FFT, SRM, etc. (Match training luma weights)
        gray = (0.299 * x[:, 0:1] + 0.587 * x[:, 1:2] + 0.114 * x[:, 2:3])
        
        # 2. Spectral Features (FFT)
        f_transform = torch.fft.fft2(gray)
        f_shift = torch.fft.fftshift(f_transform)
        mag_spec = torch.log(torch.abs(f_shift) + 1e-8)
        
        # --- STABILITY FIX: FFT Normalization (Matching Training) ---
        # Normalize per sample in batch
        batch_size = mag_spec.size(0)
        mag_spec_flat = mag_spec.view(batch_size, -1)
        mean = mag_spec_flat.mean(dim=1).view(batch_size, 1, 1, 1)
        std = mag_spec_flat.std(dim=1).view(batch_size, 1, 1, 1)
        mag_spec = (mag_spec - mean) / (std + 1e-8)
        
        spec_feat = self.spectral_branch(mag_spec)
        
        # 3. SPAI Masking
        h, w = mag_spec.shape[-2:]
        mask = torch.ones_like(mag_spec)
        mask[:, :, h//4:3*h//4, w//4:3*w//4] = 0
        spai_feat = self.spai_branch(mag_spec * mask)
        
        # 4. SRM Features
        srm_feat = self.srm_branch(self.srm_conv(gray))
        
        # 5. Chroma Features (YCbCr)
        r, g, b = x[:, 0:1], x[:, 1:2], x[:, 2:3]
        cb = -0.1687 * r - 0.3313 * g + 0.5 * b
        cr = 0.5 * r - 0.4187 * g - 0.0813 * b
        chroma = torch.cat([cb, cr], dim=1)
        chroma_feat = self.chroma_branch(chroma)
        
        # 6. Robustness (Feature Drift)
        with torch.no_grad():
            noise = torch.randn_like(x) * 0.05
            noisy_feat = self.semantic_branch(x + noise)
        robust_feat = self.robustness_branch(torch.abs(sem_feat - noisy_feat))

        # Combined Fusion
        combined = torch.cat((sem_feat, spec_feat, spai_feat, srm_feat, chroma_feat, robust_feat), dim=1)
        return self.fusion_head(combined)


def load_state_dict_from_path(path: str) -> dict:
    model_path = Path(path)
    if model_path.is_dir():
        # Look for the .pth file in the directory (specific to user's layout)
        weights_file = model_path / "argusai_best_weights.pth"
        if weights_file.exists():
            load_path = str(weights_file)
        else:
            # Fallback to any .pth or .pt file
            candidates = list(model_path.glob("*.pth")) + list(model_path.glob("*.pt"))
            if candidates:
                load_path = str(candidates[0])
            else:
                # Support torch-exported directory layouts that contain data.pkl/data/*
                if (model_path / "data.pkl").exists():
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pt")
                    tmp.close()
                    with zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                        for file_path in model_path.rglob("*"):
                            if file_path.is_file():
                                arcname = str(Path(model_path.name) / file_path.relative_to(model_path))
                                zf.write(file_path, arcname)
                    load_path = tmp.name
                else:
                    raise FileNotFoundError(f"No .pth or .pt weights found in {path}")
    else:
        load_path = str(model_path)
    
    return torch.load(load_path, map_location="cpu")
