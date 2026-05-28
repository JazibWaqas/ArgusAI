import os
import io
import math
import torch
import torch.nn as nn
import torch.optim as optim
import torch.fft
from torch.utils.data import DataLoader, random_split, ConcatDataset, Dataset
from torch.utils.checkpoint import checkpoint
from torchvision import datasets
from torchvision.transforms import v2
import torch.nn.functional as F
from PIL import Image
import timm
from datasets import load_dataset
from tqdm import tqdm
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score

# --- 1. CONFIGURATION (Kaggle T4 Optimized) ---
TRAIN_DIR = '/kaggle/input/datasets/ayushmandatta1/deepdetect-2025/ddata/train'
TEST_DIR = '/kaggle/input/datasets/ayushmandatta1/deepdetect-2025/ddata/test'

BATCH_SIZE = 16          # Optimized for 6-branch VRAM
ACCUMULATION_STEPS = 4   # Effective Batch Size = 64
NUM_EPOCHS = 15
DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Differential Learning Rates
SEMANTIC_LR = 1e-5       # Conservative for pretrained backbone
HEAD_LR = 1e-4           # Aggressive for forensic branches

PATIENCE = 3             # Number of epochs to wait for improvement
trigger_times = 0        # Counter for how many epochs have passed without improvement
best_val_loss = float('inf')

# --- 2. SIGNAL EXTRACTION (CPU-Side Utility) ---
def extract_forensic_signals(img_tensor):
    """
    Computes forensic signals from a normalized image tensor.
    IMPORTANT: img_tensor is already normalized (mean/std).
    """
    # Grayscale for FFT and SRM (using standard luma weights)
    gray = (0.299 * img_tensor[0] + 0.587 * img_tensor[1] + 0.114 * img_tensor[2]).unsqueeze(0)

    # FFT (Spectral Analysis)
    f_transform = torch.fft.fft2(gray)
    f_shift = torch.fft.fftshift(f_transform)
    # Log magnitude for compression of dynamic range
    mag_spec = torch.log(torch.abs(f_shift) + 1e-8)
    
    # --- STABILITY FIX: FFT Normalization ---
    # Normalizing magnitude to mean 0, std 1 ensures FFT features don't drown out
    # semantic features in the fusion head.
    mag_spec = (mag_spec - mag_spec.mean()) / (mag_spec.std() + 1e-8)
    
    # YCbCr (Chroma Analysis)
    r, g, b = img_tensor[0], img_tensor[1], img_tensor[2]
    cb = -0.1687 * r - 0.3313 * g + 0.5 * b
    cr = 0.5 * r - 0.4187 * g - 0.0813 * b
    chroma = torch.stack([cb, cr], dim=0)

    # Noisy version for RA-Det (Behavioral Drift/Robustness)
    noise = torch.randn_like(img_tensor) * 0.05
    noisy_img = img_tensor + noise

    return mag_spec, chroma, noisy_img

# --- 3. DATASET WRAPPERS ---
class ArgusAIDataset(Dataset):
    def __init__(self, base_dataset, transform=None, is_defactify=False):
        self.base_dataset = base_dataset
        self.transform = transform
        self.is_defactify = is_defactify

    def __len__(self):
        return len(self.base_dataset)

    def __getitem__(self, idx):
        if self.is_defactify:
            item = self.base_dataset[idx]
            img, label, gen = item['Image'].convert("RGB"), item['Label_A'], item['Label_B']
            # Defactify: 0 = Real, 1 = AI
        else:
            img, label = self.base_dataset[idx]
            # DeepDetect ImageFolder: 'fake' folder index=0, 'real' folder index=1
            # Flip to match Defactify (Real=0, AI/Fake=1)
            label = 1 - label 
            gen = -1

        if self.transform:
            img = self.transform(img)
        
        mag_spec, chroma, noisy_img = extract_forensic_signals(img)
        
        return {
            'img': img,
            'mag_spec': mag_spec,
            'chroma': chroma,
            'noisy_img': noisy_img,
            'label': label,
            'gen': gen
        }

# --- 4. DATA LOADING LOGIC ---
train_transforms = v2.Compose([
    v2.Resize((224, 224)),
    v2.RandomHorizontalFlip(),
    v2.ColorJitter(0.1, 0.1, 0.1),
    v2.ToImage(),
    v2.ToDtype(torch.float32, scale=True),
    v2.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

print("Loading and Wrapping Datasets...")
raw_dd_train = datasets.ImageFolder(root=TRAIN_DIR)
dd_val_size = int(0.1 * len(raw_dd_train))
dd_train_sub, dd_val_sub = random_split(raw_dd_train, [len(raw_dd_train)-dd_val_size, dd_val_size])

df_full = load_dataset("Rajarshi-Roy-research/Defactify_Image_Dataset", split="train+validation+test")
df_split = df_full.train_test_split(test_size=0.2, seed=42)

train_ds = ConcatDataset([
    ArgusAIDataset(dd_train_sub, transform=train_transforms),
    ArgusAIDataset(df_split['train'], transform=train_transforms, is_defactify=True)
])

train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=2, pin_memory=True, drop_last=True)
val_ds = ArgusAIDataset(dd_val_sub, transform=train_transforms)
val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=2, pin_memory=True)

# --- 5. THE CORE-6 MODEL ---
class ArgusAIFUSE(nn.Module):
    def __init__(self, num_classes=2):
        super(ArgusAIFUSE, self).__init__()
        self.semantic_branch = timm.create_model('convnext_small.fb_in22k_ft_in1k', pretrained=True, num_classes=0)
        self.spectral_branch = nn.Sequential(
            nn.AdaptiveAvgPool2d((64, 64)), nn.Flatten(),
            nn.Linear(64*64, 256), nn.ReLU()
        )
        self.spai_branch = nn.Sequential(
            nn.Conv2d(1, 32, 3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d((32, 32)), nn.Flatten(),
            nn.Linear(32*32*32, 256)
        )
        self.srm_conv = nn.Conv2d(1, 3, 5, padding=2, bias=False)
        self.srm_branch = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d((16, 16)), nn.Flatten(),
            nn.Linear(32*16*16, 256)
        )
        self.chroma_branch = nn.Sequential(
            nn.Conv2d(2, 16, 3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d((32, 32)), nn.Flatten(),
            nn.Linear(16*32*32, 128)
        )
        self.robustness_branch = nn.Sequential(
            nn.Linear(768, 256), nn.ReLU(), nn.Linear(256, 128)
        )
        self.fusion_head = nn.Sequential(
            nn.Linear(1792, 1024),
            nn.ReLU(), nn.Dropout(0.3), nn.Linear(1024, num_classes)
        )

    def forward(self, batch):
        sem_feat = checkpoint(self.semantic_branch, batch['img'], use_reentrant=False)
        with torch.no_grad():
            noisy_feat = self.semantic_branch(batch['noisy_img'])
        spec_feat = self.spectral_branch(batch['mag_spec'])
        
        h, w = batch['mag_spec'].shape[-2:]
        mask = torch.ones_like(batch['mag_spec'])
        mask[:, :, h//4:3*h//4, w//4:3*w//4] = 0
        spai_feat = self.spai_branch(batch['mag_spec'] * mask)

        gray = (0.299 * batch['img'][:, 0] + 0.587 * batch['img'][:, 1] + 0.114 * batch['img'][:, 2]).unsqueeze(1)
        srm_feat = self.srm_branch(self.srm_conv(gray))
        chroma_feat = self.chroma_branch(batch['chroma'])
        robust_feat = self.robustness_branch(torch.abs(sem_feat - noisy_feat))

        combined = torch.cat((sem_feat, spec_feat, spai_feat, srm_feat, chroma_feat, robust_feat), dim=1)
        return self.fusion_head(combined)

# --- 6. TRAINING & VALIDATION EXECUTION ---
model = ArgusAIFUSE().to(DEVICE).to(memory_format=torch.channels_last)

optimizer = optim.AdamW([
    {'params': model.semantic_branch.parameters(), 'lr': SEMANTIC_LR},
    {'params': model.spectral_branch.parameters(), 'lr': HEAD_LR},
    {'params': model.spai_branch.parameters(), 'lr': HEAD_LR},
    {'params': model.srm_branch.parameters(), 'lr': HEAD_LR},
    {'params': model.chroma_branch.parameters(), 'lr': HEAD_LR},
    {'params': model.robustness_branch.parameters(), 'lr': HEAD_LR},
    {'params': model.fusion_head.parameters(), 'lr': HEAD_LR},
], weight_decay=0.05)

total_steps_per_epoch = math.ceil(len(train_loader) / ACCUMULATION_STEPS)
scheduler = optim.lr_scheduler.OneCycleLR(optimizer, max_lr=[SEMANTIC_LR] + [HEAD_LR]*6, epochs=NUM_EPOCHS, steps_per_epoch=total_steps_per_epoch)
scaler = torch.amp.GradScaler('cuda')
criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

def get_validation_metrics(model, loader):
    model.eval()
    total_loss = 0
    all_preds, all_labels = [], []
    with torch.no_grad():
        for batch in loader:
            batch = {k: v.to(DEVICE) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}
            with torch.amp.autocast('cuda'):
                outputs = model(batch)
                loss = criterion(outputs, batch['label'])
            total_loss += loss.item()
            _, predicted = outputs.max(1)
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(batch['label'].cpu().numpy())
            
    val_loss = total_loss / len(loader)
    val_acc = 100. * np.sum(np.array(all_preds) == np.array(all_labels)) / len(all_labels)
    val_f1 = f1_score(all_labels, all_preds, average='binary')
    val_pre = precision_score(all_labels, all_preds, average='binary', zero_division=0)
    val_rec = recall_score(all_labels, all_preds, average='binary', zero_division=0)
    return val_loss, val_acc, val_f1, val_pre, val_rec

def train_epoch(loader, epoch):
    model.train()
    optimizer.zero_grad(set_to_none=True)
    running_loss, correct, total = 0.0, 0, 0
    loop = tqdm(loader, desc=f"Epoch {epoch+1}/{NUM_EPOCHS}")
    for i, batch in enumerate(loop):
        batch = {k: v.to(DEVICE) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}
        batch['img'] = batch['img'].to(memory_format=torch.channels_last)
        batch['noisy_img'] = batch['noisy_img'].to(memory_format=torch.channels_last)
        with torch.amp.autocast('cuda'):
            outputs = model(batch)
            loss = criterion(outputs, batch['label']) / ACCUMULATION_STEPS
        scaler.scale(loss).backward()
        if (i + 1) % ACCUMULATION_STEPS == 0 or (i + 1) == len(loader):
            scaler.step(optimizer)
            scaler.update()
            optimizer.zero_grad(set_to_none=True)
            if scheduler.last_epoch < scheduler.total_steps:
                scheduler.step()
        running_loss += loss.item() * ACCUMULATION_STEPS
        _, predicted = outputs.max(1)
        total += batch['label'].size(0)
        correct += predicted.eq(batch['label']).sum().item()
        loop.set_postfix(loss=running_loss/(i+1), acc=f"{100.*correct/total:.2f}%")
    torch.save(model.state_dict(), 'argusai_latest.pth')
    return running_loss / len(loader), 100. * correct / total

if __name__ == "__main__":
    best_val_loss, trigger_times = float('inf'), 0
    if os.path.exists('argusai_latest.pth'):
        model.load_state_dict(torch.load('argusai_latest.pth', map_location=DEVICE))

    print(f"Starting ArgusAI Core-6 (0=Real, 1=AI) with Patience: {PATIENCE}...")
    
    # --- DIAGNOSTIC: Label Consistency Check ---
    it = iter(train_loader)
    first_batch = next(it)
    print(f"DIAGNOSTIC: Labels in batch 1: {first_batch['label'].tolist()}")
    print(f"DIAGNOSTIC: Distribution: Real={(first_batch['label']==0).sum()}, AI={(first_batch['label']==1).sum()}")

    for epoch in range(NUM_EPOCHS):
        train_loss, train_acc = train_epoch(train_loader, epoch)
        val_loss, val_acc, val_f1, val_pre, val_rec = get_validation_metrics(model, val_loader)
        print(f"Epoch {epoch+1} | Val Loss: {val_loss:.4f} | Acc: {val_acc:.2f}% | F1: {val_f1:.4f} | Pre: {val_pre:.4f} | Rec: {val_rec:.4f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), 'argusai_best_weights.pth')
            trigger_times = 0
        else:
            trigger_times += 1
            if trigger_times >= PATIENCE:
                print("Early stopping triggered!")
                break
